from pathlib import Path
import math
import wave
import numpy as np
import pytest
from PIL import Image

from phrasync.footage import prepare_footage, effects_enabled
from phrasync.storage import store_path, delete_asset
from phrasync.audio_spectrum import SpectrumSource


def test_footage_rewrites_client_url_and_keeps_original_project(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (320, 320), "red").save(path)
    asset = store_path("image", path)
    project = {"background": {"footageEnabled": True, "clips": [{"id": "clip", "asset": {**asset.public(), "url": "https://untrusted.invalid/file"}, "start": 0, "end": 2}]}}
    try:
        cleaned = prepare_footage(project)
        assert cleaned["background"]["clips"][0]["asset"]["url"] == asset.url
        assert project["background"]["clips"][0]["asset"]["url"].startswith("https:")
        assert cleaned["background"]["clips"][0]["rate"] == 1
    finally:
        delete_asset(asset.id)


def test_footage_requires_existing_media_and_valid_effects():
    with pytest.raises(ValueError, match="Add images"):
        prepare_footage({"background": {"footageEnabled": True}})
    with pytest.raises(ValueError, match="Invalid footage effect"):
        prepare_footage({"background": {"effects": {"flash": 1000}}})
    with pytest.raises(ValueError, match="missing"):
        prepare_footage({"background": {"footageEnabled": True, "clips": [{"asset": {"id": "not-real", "kind": "image"}}]}})
    assert not effects_enabled({"background": {"effects": {"bpm": 120}}})
    assert effects_enabled({"background": {"effects": {"spectrum": 10}}})


def test_integrated_visual_tracks_and_transitions_are_validated():
    import copy
    project = {"background": {"footageEnabled": True, "tracks": ["V1", "V2"], "clips": [
        {"id":"visual", "asset":{"kind":"visual", "id":"visual-ocean", "settings":{"visual":"scene3d", "sceneKit":"ocean"}},
         "start":0, "end":2, "track":1, "opacity":.5, "transition":"fade", "fadeIn":.35}]}}
    assert prepare_footage(project)["background"]["clips"][0]["opacity"] == .5
    for key, value in [("track",4),("opacity",2),("transition","unknown"),("fadeIn",float("nan"))]:
        invalid = copy.deepcopy(project); invalid["background"]["clips"][0][key] = value
        with pytest.raises(ValueError): prepare_footage(invalid)
    invalid = copy.deepcopy(project)
    invalid["background"]["clips"][0]["asset"]["settings"]["visual"] = "unknown"
    with pytest.raises(ValueError, match="Unknown integrated visual"): prepare_footage(invalid)


def test_spectrum_tracks_frequency_and_has_bounded_memory(tmp_path):
    path = tmp_path / "tone.wav"
    rate = 8000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(rate)
        signal = np.sin(np.arange(rate) * 2 * math.pi * 440 / rate) * 12000
        handle.writeframes(signal.astype(np.int16).tobytes())
    spectrum = SpectrumSource(str(path), 25)
    try:
        for frame in range(15):
            bands = spectrum.read(frame)
        expected = round(440 / (48000 / 256))
        assert abs(int(np.argmax(bands)) - expected) <= 1
        assert max(bands) > .5 and len(bands) == 128
        assert spectrum.window.size == 256
    finally:
        spectrum.close()
