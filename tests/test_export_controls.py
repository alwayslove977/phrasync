import base64
import io
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from fastapi.testclient import TestClient

import app as app_module
from phrasync.encoding import bitrate_bps, rate_control_args
from phrasync.webgl_renderer import _encode_canvas_ffmpeg
from phrasync.media import decode_test


def test_custom_rate_is_not_capped_at_28_mbps():
    for value in [1, 50, 150, 300]:
        project = {"export": {"bitrateMbps": value, "crf": 18}}
        assert bitrate_bps(project) == value * 1_000_000
        args = rate_control_args(project)
        assert args[args.index("-b:v") + 1] == str(value * 1_000_000)
        assert "-crf" not in args
    assert rate_control_args({"export": {"crf": 21}}) == ["-crf", "21"]


@pytest.mark.parametrize("value", [0, -1, "invalid", float("nan"), float("inf")])
def test_invalid_custom_rate_is_rejected(value):
    with pytest.raises(ValueError):
        bitrate_bps({"export": {"bitrateMbps": value}})


def test_api_requires_selected_destination_even_for_desktop(tmp_path, monkeypatch):
    client = TestClient(app_module.app)
    monkeypatch.setattr(app_module.desktop_export, "_window", object())
    monkeypatch.setattr(app_module.desktop_export, "_directory_selected", False)
    queued = Mock()
    monkeypatch.setattr(app_module.manager, "create_render", queued)
    response = client.post("/api/render", json={"project": {}, "outputDirectory": str(tmp_path)})
    assert response.status_code == 400
    assert "Choose" in response.json()["detail"]
    queued.assert_not_called()
    monkeypatch.setattr(app_module.desktop_export, "_window", None)
    assert client.post("/api/render", json={"project": {}}).status_code == 400
    assert client.post("/api/render", json={"project": {}, "outputDirectory": "relative"}).status_code == 400


def test_show_export_does_not_copy_or_create_a_second_mp4(tmp_path, monkeypatch):
    source = tmp_path / "My project.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr("phrasync.desktop_export.manager.output_path", lambda _: source)
    launched = Mock()
    monkeypatch.setattr("phrasync.desktop_export.subprocess.Popen", launched)
    assert app_module.desktop_export.show_render_file("job") == str(source)
    assert list(tmp_path.iterdir()) == [source]
    assert launched.call_args.args[0] == ["explorer.exe", "/select,", str(source)]


def test_4k_canvas_can_encode_without_browser_h264(tmp_path):
    import re
    import urllib.request
    image = Image.new("RGBA", (3840, 2160), "#406080")
    devtools = Mock()
    def send_frame(expression):
        import json
        endpoint = re.search(r'VFFrameTransport.send\(VFExport.canvas\(\),"([^\"]+)"', expression).group(1)
        frames = json.loads(re.search(r'const frames=(.*?);for', expression).group(1))
        for _ in frames:
            request = urllib.request.Request(endpoint, data=image.tobytes(), headers={'Origin': 'http://127.0.0.1:5526'})
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.status == 204
        return True
    devtools.evaluate.side_effect = send_frame
    output = tmp_path / "4k.h264"
    _encode_canvas_ffmpeg(devtools, {"__renderOrigin": "http://127.0.0.1:5526", "export": {"bitrateMbps": 150, "preset": "ultrafast"}},
                          output, width=3840, height=2160, fps=30, frame_count=3, envelope=[0, 0, 0])
    assert output.stat().st_size > 0
    assert devtools.evaluate.call_count == 1
    ok, details = decode_test(output)
    assert ok, details


def test_cancelled_compatibility_render_removes_partial_stream(tmp_path):
    output = tmp_path / "partial.h264"
    with pytest.raises(RuntimeError, match="cancelled"):
        _encode_canvas_ffmpeg(Mock(), {"__renderOrigin": "http://127.0.0.1:5526"}, output, width=320, height=320, fps=30,
                              frame_count=2, envelope=[], cancel_check=lambda: True)
    assert not output.exists()


@pytest.mark.parametrize('fps', [12, 23, 24, 25, 30, 50, 60])
def test_canvas_intermediate_preserves_exact_frame_timestamps(tmp_path, fps):
    av = pytest.importorskip('av')
    import json
    import math
    import re
    import urllib.request
    output = tmp_path / f'exact-{fps}.h264'
    pixels = Image.new('RGBA', (320, 320), '#406080').tobytes()
    origin = 'http://127.0.0.1:5526'
    def send_frames(expression):
        endpoint = re.search(r'VFFrameTransport.send\(VFExport.canvas\(\),"([^\"]+)"', expression).group(1)
        frames = json.loads(re.search(r'const frames=(.*?);for', expression).group(1))
        for _ in frames:
            with urllib.request.urlopen(urllib.request.Request(endpoint, data=pixels, headers={'Origin': origin}), timeout=10) as response:
                assert response.status == 204
        return {'mode': 'raw'}
    devtools = Mock()
    devtools.evaluate.side_effect = send_frames
    count = math.ceil(.6 * fps)
    _encode_canvas_ffmpeg(devtools, {'__renderOrigin': origin, 'export': {'preset': 'ultrafast'}},
                         output, width=320, height=320, fps=fps, frame_count=count, envelope=[])
    with av.open(str(output)) as container:
        assert float(container.streams.video[0].average_rate) == fps
        frames = list(container.decode(video=0))
        assert len(frames) == count
        for index, frame in enumerate(frames):
            assert float(frame.pts * frame.time_base) == pytest.approx(index / fps, abs=1e-8)


def test_project_named_outputs_do_not_overwrite_previous_exports(tmp_path, monkeypatch):
    import phrasync.jobs as jobs
    from types import SimpleNamespace
    manager = jobs.JobManager()
    monkeypatch.setattr(manager, "_save", lambda job: None)
    report = SimpleNamespace(ok=True, public=lambda: {"ok": True})
    monkeypatch.setattr(jobs, "preflight_project", lambda _: report)
    monkeypatch.setattr(jobs, "postflight_render", lambda *args, **kwargs: report)
    def render(project, path, **kwargs):
        path.write_bytes(b"rendered video")
        return {"path": str(path), "duration": 1}
    monkeypatch.setattr(jobs, "render_project", render)
    original = tmp_path / "My_song.mp4"
    original.write_bytes(b"existing user video")
    for job_id in ["one", "two"]:
        manager.jobs[job_id] = jobs.Job(id=job_id, kind="render")
        manager._run_render(job_id, {}, "My song", tmp_path)
        assert manager.jobs[job_id].state == "complete"
    assert original.read_bytes() == b"existing user video"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["My_song (2).mp4", "My_song (3).mp4", "My_song.mp4"]
    manager.executor.shutdown()
