"""Real headless export through the app, not a mocked WebGL renderer."""
import socket
import threading
import time

import pytest
import uvicorn

from phrasync.config import ASSETS_DIR
from phrasync import font_utils, storage
from phrasync.media import decode_test
from phrasync.renderer import render_project
from phrasync.subtitles import parse_lrc


@pytest.mark.parametrize("text_space", ["flat", "scene"])
def test_cjk_custom_font_and_timing_in_real_webgl_export(tmp_path, monkeypatch, text_space):
    from app import app
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(font_utils, "UPLOADS_DIR", uploads)
    media_app = next(route.app for route in app.routes if getattr(route, "path", None) == "/media")
    monkeypatch.setattr(media_app, "all_directories", [str(uploads)])
    font_utils.refresh_fonts()
    asset = storage.store_path("font", ASSETS_DIR / "NotoSansJP-VF.ttf")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(.05)
        assert server.started
        project = {"title": "CJK WebGL regression", "duration": 1,
                   "canvas": {"width": 320, "height": 320, "fps": 12},
                   "__renderOrigin": f"http://127.0.0.1:{port}",
                   "background": {"type": "dynamic", "visual": "scene3d", "textSpace": text_space,
                                  "sceneKit": "ocean", "sceneSpeed": 1, "grain": 0},
                   "style": {"preset": "wipe-fill", "fontPreset": "impact", "fontAssetId": asset.id,
                             "fontSize": 120, "uppercase": False},
                   "cues": parse_lrc("[00:00]日[00:00.30]本[00:00.60]語<00:01>"),
                   "exportRange": {"in": .25, "out": .75},
                   "export": {"crf": 25, "preset": "ultrafast", "bitrateMbps": 3}}
        output = tmp_path / f"cjk-{text_space}.mp4"
        result = render_project(project, output)
        assert result["frames"] == 6
        assert output.is_file() and output.stat().st_size > 0
        assert decode_test(output)[0]
        assert not list(tmp_path.glob("*.partial.*"))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        font_utils.refresh_fonts()
