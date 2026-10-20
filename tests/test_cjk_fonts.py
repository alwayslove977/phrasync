from pathlib import Path
import io
import asyncio

import pytest
from PIL import ImageFont

from phrasync import font_utils, storage
from phrasync.subtitles import parse_lrc


@pytest.fixture
def isolated_fonts(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(font_utils, "UPLOADS_DIR", tmp_path)
    font_utils.refresh_fonts()
    yield tmp_path
    font_utils.refresh_fonts()


def test_font_upload_validates_deduplicates_and_preserves_unicode_name(isolated_fonts):
    source = font_utils.resolve_font_path("modern")
    assert source
    payload = source.read_bytes()
    name = "王汉宗中行书繁" + source.suffix
    first = storage.store_stream("font", name, io.BytesIO(payload))
    second = storage.store_stream("font", name, io.BytesIO(payload))
    third = storage.store_path("font", Path(first.path), name)
    assert first.id == second.id == third.id
    assert first.name == name
    assert storage.get_asset(first.id, "font").name == name
    assert len(list(isolated_fonts.glob("font-*" + source.suffix))) == 1
    assert len(list(isolated_fonts.glob("*.meta.json"))) == 1
    assert Path(first.path) in font_utils.index_fonts().values()
    with pytest.raises(ValueError, match="valid TTF"):
        storage.store_stream("font", "broken.ttf", io.BytesIO(b"not a font"))
    assert len(list(isolated_fonts.iterdir())) == 2


def test_streamed_upload_uses_same_deduplication(isolated_fonts):
    source = font_utils.resolve_font_path("modern")
    data = source.read_bytes()
    first = storage.store_path("font", source)
    async def chunks():
        for i in range(0, len(data), 20000):
            yield data[i:i + 20000]
    second = asyncio.run(storage.store_chunks("font", source.name, chunks(), len(data)))
    assert first.id == second.id
    assert len(list(isolated_fonts.iterdir())) == 2


def test_local_font_library_can_be_selected_via_api(isolated_fonts, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import app
    media_app = next(route.app for route in app.routes if getattr(route, "path", None) == "/media")
    monkeypatch.setattr(media_app, "all_directories", [str(isolated_fonts)])
    source = font_utils.resolve_font_path("modern")
    folder = tmp_path / "local fonts"
    folder.mkdir()
    path = folder / ("用户字体" + source.suffix)
    path.write_bytes(source.read_bytes())
    monkeypatch.setattr(font_utils, "custom_font_directories", lambda: [folder])
    client = TestClient(app)
    fonts = client.get("/api/fonts").json()["fonts"]
    assert len(fonts) == 1
    assert fonts[0]["name"] == path.name
    assert fonts[0]["family"]
    assert "path" not in fonts[0]
    selected = client.post(f"/api/fonts/{fonts[0]['id']}/select")
    assert selected.status_code == 200
    assert selected.json()["name"] == path.name
    assert client.get(selected.json()["url"]).content == path.read_bytes()
    assert client.post("/api/fonts/not-a-font/select").status_code == 404


def test_font_upload_http_routes_agree_and_reject_corrupt_files(isolated_fonts):
    from fastapi.testclient import TestClient
    from app import app
    client = TestClient(app)
    source = font_utils.resolve_font_path("modern")
    data = source.read_bytes()
    name = "中文字体" + source.suffix
    multipart = client.post("/api/assets/font", files={"file": (name, data, "font/ttf")})
    streamed = client.post("/api/assets/font/stream", params={"filename": name}, content=data)
    assert multipart.status_code == streamed.status_code == 200
    assert multipart.json()["id"] == streamed.json()["id"]
    assert streamed.json()["name"] == name
    corrupt = client.post("/api/assets/font/stream", params={"filename": "bad.ttf"}, content=b"broken")
    assert corrupt.status_code == 400
    assert "valid TTF" in corrupt.json()["detail"]
    assert len(list(isolated_fonts.iterdir())) == 2


def test_cjk_fallback_searches_beyond_japanese_shortlist(monkeypatch):
    class FakeFont:
        size = 32
        def __init__(self, supported): self.supported = supported
        def getmask(self, char):
            class Mask(bytes):
                size = (1, 1)
            return Mask(b"x" if char in self.supported else b"?")
    primary, fallback = FakeFont("ABC"), FakeFont("词한국")
    path = Path("STHeiti Medium.ttc")
    monkeypatch.setattr(font_utils, "load_font", lambda *args: primary)
    monkeypatch.setattr(font_utils, "index_fonts", lambda: {path.name.lower(): path})
    monkeypatch.setattr(font_utils, "_load_font_cached", lambda *args: fallback)
    font_utils.load_font_for_text.cache_clear()
    try:
        assert font_utils.load_font_for_text(32, "modern", "词한국") is fallback
        assert font_utils.load_font_for_text(32, "modern", "ABC") is primary
        with pytest.raises(ValueError, match=r"CJK.*U\+4E2D.*Checked"):
            font_utils.load_font_for_text(32, "modern", "中")
    finally:
        font_utils.load_font_for_text.cache_clear()


@pytest.mark.parametrize("text", ["词语简体中文", "繁體中文歌詞", "日本語こんにちは", "한국어가사"])
def test_real_cjk_glyph_coverage_and_mp4_export(tmp_path, text):
    from phrasync.renderer import render_project
    from phrasync.media import decode_test
    from phrasync.qa import preflight_project
    font = font_utils.load_font_for_text(32, "impact", text)
    assert font_utils._covers_japanese_text(font, text)
    cue = parse_lrc(f"[00:00]<00:00>{text}<00:00.50>")[0]
    project = {"title": "CJK test", "duration": .5,
               "canvas": {"width": 320, "height": 320, "fps": 12},
               "background": {"type": "dynamic", "visual": "aurora", "grain": 0},
               "style": {"preset": "wipe-fill", "fontPreset": "impact", "fontSize": 110},
               "cues": [cue], "exportRange": {"enabled": True, "in": 0, "out": .5},
               "export": {"crf": 25, "preset": "ultrafast"}}
    report = preflight_project(project)
    assert not [issue for issue in report.issues if issue.code == "font_coverage"], report.public()
    output = tmp_path / "cjk.mp4"
    result = render_project(project, output)
    assert output.is_file() and output.stat().st_size > 0
    assert result["frames"] == 6
    assert decode_test(output)[0]
