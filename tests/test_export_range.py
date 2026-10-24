from pathlib import Path
import pytest
from phrasync.renderer import _build_context, render_project
from phrasync.media import probe_duration, decode_test, run_ffmpeg
from phrasync.storage import store_path


def project():
    return {"duration":10,"canvas":{"width":320,"height":320,"fps":24},
            "background":{"type":"dynamic","visual":"aurora"},
            "style":{"fontPreset":"modern"},
            "cues":[{"id":"a","start":5,"end":6,"text":"RANGE"}],
            "exportRange":{"in":5,"out":6},"export":{"preset":"ultrafast"}}


def test_range_context_retains_absolute_lyrics_and_uses_short_duration():
    ctx=_build_context(project())
    assert ctx.start_time==5 and ctx.duration==1 and ctx.frame_count==24
    assert ctx.cues[0]["start"]==5
    assert len(ctx.envelope)==24


@pytest.mark.parametrize("selected",[{"in":6,"out":5},{"in":-1,"out":6},{"in":5,"out":11},{"in":5,"out":float("nan")}])
def test_invalid_ranges_rejected(selected):
    p=project();p["exportRange"]=selected
    with pytest.raises(ValueError):_build_context(p)


def test_manual_duration_can_shorten_or_extend_timeline():
    p=project();del p["exportRange"]
    for value in [2,20]:
        p["timelineDuration"]=value
        assert _build_context(p).duration==value


def test_real_short_range_export(tmp_path):
    output=tmp_path/"range.mp4"
    result=render_project(project(),output)
    assert result["duration"]==1 and result["frames"]==24
    assert abs(probe_duration(output)-1)<.05
    assert decode_test(output)[0]


@pytest.mark.parametrize('fps', [12, 23, 24, 25, 30, 50, 60])
def test_decimal_range_does_not_add_a_phantom_frame(fps):
    import math
    p = project()
    p['canvas']['fps'] = fps
    p['exportRange'] = {'in': .2, 'out': .8}
    assert _build_context(p).frame_count == math.ceil(.6 * fps - 1e-9)


@pytest.mark.parametrize('fps', [12, 30, 60])
def test_real_single_frame_range_passes_postflight(tmp_path, fps):
    from phrasync.qa import postflight_render
    p = project()
    p['canvas']['fps'] = fps
    p['exportRange'] = {'in': .4, 'out': .4 + 1/fps}
    output = tmp_path / f'one-frame-{fps}.mp4'
    result = render_project(p, output)
    assert result['frames'] == 1
    report = postflight_render(output, 1/fps)
    assert report.ok, report.public()


@pytest.mark.parametrize('duration', [None, 0, -1, float('nan')])
def test_postflight_rejects_a_missing_or_invalid_duration(tmp_path, monkeypatch, duration):
    import phrasync.qa as critic
    output = tmp_path / 'invalid.mp4'
    output.write_bytes(b'x' * 2048)
    monkeypatch.setattr(critic, 'decode_test', lambda _: (True, ''))
    monkeypatch.setattr(critic, 'probe_duration', lambda _: duration)
    report = critic.postflight_render(output, 1)
    assert not report.ok
    assert any(issue.code == 'duration_zero' for issue in report.issues)


def test_audio_is_cut_from_in_not_from_song_start(tmp_path):
    import numpy as np
    source=tmp_path/"tone.wav"
    run_ffmpeg(["-y","-f","lavfi","-i","sine=frequency=900:sample_rate=8000:duration=7",
                "-af","volume=enable='lt(t,5)':volume=0",str(source)],check=True)
    asset=store_path("audio",source)
    try:
        p=project();p["audioAssetId"]=asset.id
        output=tmp_path/"audio-range.mp4"
        render_project(p,output)
        decoded=run_ffmpeg(["-i",str(output),"-vn","-ac","1","-ar","8000","-f","f32le","pipe:1"],check=True)
        samples=np.frombuffer(decoded.stdout,dtype=np.float32)
        assert np.sqrt(np.mean(samples**2))>.03
        assert abs(probe_duration(output)-1)<.08
    finally:
        Path(asset.path).unlink(missing_ok=True)
