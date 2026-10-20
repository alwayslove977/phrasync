"""Check the actual compiled 0.4.8 server before Store packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5558")
    args = parser.parse_args()

    def call(path, payload=None, binary=None):
        data = binary if binary is not None else json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(args.url + path, data=data,
            headers={"Content-Type": "application/octet-stream" if binary is not None else "application/json"})
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)

    identity = call("/api/instance")
    assert identity["version"] == "0.4.8", identity
    for filename in ("app-fonts.js", "app-render.js", "app-workflows.js", "kinetic.js"):
        with urllib.request.urlopen(args.url + "/static/" + filename) as response:
            packaged = response.read()
        assert hashlib.sha256(packaged).digest() == hashlib.sha256((ROOT / "static" / filename).read_bytes()).digest(), filename

    lrc = "[00:00]李[00:00.247]清[00:00.534]照[00:01]"
    lyric_asset = call("/api/assets/lyrics/stream?filename=compiled-test.lrc", binary=lrc.encode("utf-8"))
    cues = call("/api/lyrics/import", {"assetId": lyric_asset["id"]})["cues"]
    assert cues[0]["text"] == "李清照"
    assert [word["start"] for word in cues[0]["words"]] == [0, .247, .534]

    font_name = "测试字体.ttf"
    font_data = Path("C:/Windows/Fonts/comic.ttf").read_bytes()
    route = "/api/assets/font/stream?filename=" + urllib.parse.quote(font_name)
    first = call(route, binary=font_data)
    second = call(route, binary=font_data)
    assert first["id"] == second["id"] and second["name"] == font_name

    output = ROOT / "qa_out/048-packaged-exports"
    output.mkdir(parents=True, exist_ok=True)
    rendered = []
    for language, text in [("simplified", "词语简体中文"), ("traditional", "繁體中文歌詞"),
                           ("japanese", "日本語こんにちは"), ("korean", "한국어가사")]:
        project = {"title": "048 packaged " + language, "duration": .5,
                   "canvas": {"width": 320, "height": 320, "fps": 12},
                   "background": {"type": "dynamic", "visual": "aurora", "grain": 0},
                   "style": {"preset": "wipe-fill", "fontPreset": "impact", "fontAssetId": first["id"], "fontSize": 110},
                   "cues": [{"id": "cjk", "start": 0, "end": .5, "text": text}],
                   "export": {"crf": 25, "preset": "ultrafast"}}
        job = call("/api/render", {"project": project, "outputDirectory": str(output)})
        deadline = time.monotonic() + 120
        while job["state"] not in {"complete", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(.2)
            job = call("/api/render/" + job["id"])
        assert job["state"] == "complete", job
        path = Path(job["result"]["path"])
        assert path.parent == output and path.stat().st_size > 0
        assert job["postflight"]["ok"], job["postflight"]
        rendered.append({"language": language, "filename": path.name, "bytes": path.stat().st_size})
        print(json.dumps(rendered[-1]), flush=True)
    report = {"version": identity["version"], "staticMatchesSource": True,
              "enhancedLrc": True, "fontDeduplication": True, "renders": rendered}
    (ROOT / "qa_out/048-packaged-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
