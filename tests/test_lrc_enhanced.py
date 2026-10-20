import json
import shutil
import subprocess
from pathlib import Path

import pytest

from phrasync.subtitles import parse_lrc, cues_to_enhanced_lrc, parse_lyrics_file


@pytest.mark.parametrize("source", [
    "[00:01.00]<00:01.00>Hello <00:01.50>world<00:02.20>",
    "[00:01.00]Hello [00:01.50]world[00:02.20]",
    "<00:01.00>Hello <00:01.50>world<00:02.20>",
])
def test_word_tags_are_parsed_without_displaying_timestamps(source):
    cue = parse_lrc(source)[0]
    assert cue["text"] == "Hello world"
    assert cue["start"] == 1
    assert cue["end"] == 2.2
    assert cue["words"] == [{"text": "Hello", "start": 1., "end": 1.5},
                            {"text": "world", "start": 1.5, "end": 2.2}]


def test_chinese_inline_tags_preserve_text_and_millisecond_timing():
    from phrasync import kinetic
    cue = parse_lrc("[00:00.000]李[00:00.747]清[00:01.234]照[00:02.000]")[0]
    assert cue["text"] == "李清照"
    assert [w["start"] for w in cue["words"]] == [0, .747, 1.234]
    assert cue["words"][-1]["end"] == 2
    assert [w["start"] for w in kinetic.cue_words(cue)] == [0, .747, 1.234]


def test_lrc_metadata_offset_repeated_lines_blank_boundaries_and_bom(tmp_path):
    source = "\ufeff[ar:Artist]\r\n[offset:+250]\r\n[00:01:250][00:05.250]Repeated\r\n[00:03.00]\r\n[00:08]Last"
    path = tmp_path / "lyrics.lrc"
    path.write_text(source, encoding="utf-8")
    cues = parse_lyrics_file(path)
    assert [c["text"] for c in cues] == ["Repeated", "Repeated", "Last"]
    assert [c["start"] for c in cues] == [1.5, 5.5, 8.25]
    assert cues[0]["end"] == 3.22
    assert all(not c["words"] for c in cues)
    assert parse_lrc("[offset:-500]\n[00:00.100]Zero")[0]["start"] == 0


def test_empty_tags_and_bad_timing_do_not_create_broken_words():
    cue = parse_lrc("[00:00]<00:00><00:01>A<00:02>B<00:03>")[0]
    assert cue["end"] == 3
    assert [w["start"] for w in cue["words"]] == [1, 2]
    with pytest.raises(ValueError, match="chronological"):
        parse_lrc("[00:00]<00:02>A<00:01>B")
    assert parse_lrc("[ar:test]\nnot timed\n[00:00]") == []


def test_enhanced_lrc_roundtrip_keeps_word_boundaries():
    cues = parse_lrc("[00:01]<00:01>Hello <00:01.50>world<00:02.20>")
    again = parse_lrc(cues_to_enhanced_lrc(cues))
    assert again[0]["words"] == cues[0]["words"]
    assert again[0]["end"] == 2.2
    untimed = parse_lrc("[00:01]Hello world")
    assert "<" not in cues_to_enhanced_lrc(untimed)


def test_repeated_enhanced_lines_shift_word_timing_together():
    cues = parse_lrc("[00:01][00:06]<00:01>Hello <00:02>world<00:03>")
    assert [c["start"] for c in cues] == [1, 6]
    assert [w["start"] for w in cues[1]["words"]] == [6, 7]
    assert cues[1]["end"] == 8


@pytest.mark.parametrize("source", ["[00:01]<00:01>你好 <00:02>世界<00:03>",
                                    "[00:01]李[00:01.747]清[00:02.234]照[00:03]"])
def test_enhanced_lrc_word_states_match_browser_engine(source):
    from phrasync import kinetic
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    cue = parse_lrc(source)[0]
    style = {"preset": "wipe-fill"}
    spec = kinetic.resolved_preset(style)
    words = kinetic.cue_words(cue)
    root = Path(__file__).resolve().parents[1]
    script = "global.window=global;\n" + (root / "static/kinetic.js").read_text(encoding="utf-8")
    script += f"\nconst cue={json.dumps(cue)}, style={json.dumps(style)};\n"
    script += "console.log(JSON.stringify([1,1.5,2,2.5].map(t=>VFKinetic.cueWords(cue).map(w=>VFKinetic.wordState(w,cue,t,VFKinetic.resolvedPreset(style),0).fill))));"
    result = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    expected = [[kinetic.word_state(w, cue, t, spec, 0).fill for w in words] for t in [1, 1.5, 2, 2.5]]
    assert json.loads(result.stdout) == expected
