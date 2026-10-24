"""Regression coverage for issue #5, including existing source environments."""
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error
import urllib.request

import numpy as np
import pytest
from PIL import Image

from phrasync.audio_spectrum import SpectrumSource
from phrasync.frame_bridge import frame_bridge
from phrasync.footage import prepare_footage
from phrasync.language_map import load_audio
from phrasync.media import run_ffmpeg
from phrasync.storage import store_path, delete_asset
from phrasync.webgl_renderer import _DevTools, _fallback_reason


@pytest.mark.parametrize('details', [
    {'text': 'Uncaught (in promise)', 'exception': {'description': 'Error: Footage is missing\n at exportBase'}},
    {'text': 'Export frame failed'},
    {'text': 'Uncaught', 'exception': {'value': 'custom rejection'}},
])
def test_browser_exception_details_are_not_discarded(details):
    devtools = object.__new__(_DevTools)
    devtools.call = Mock(return_value={'result': {'type': 'object'}, 'exceptionDetails': details})
    with pytest.raises(RuntimeError, match='Export browser:') as error:
        devtools.evaluate('Promise.reject(new Error())')
    assert (details.get('exception', {}).get('description') or
            details.get('exception', {}).get('value') or details['text']) in str(error.value)


def test_browser_evaluation_retains_values_and_legacy_errors():
    devtools = object.__new__(_DevTools)
    devtools.call = Mock(return_value={'result': {'value': {'frames': 8}}})
    assert devtools.evaluate('frames') == {'frames': 8}
    devtools.call.return_value = {'result': {'subtype': 'error', 'description': 'encoder stopped'}}
    with pytest.raises(RuntimeError, match='encoder stopped'):
        devtools.evaluate('encode')


def test_legacy_background_metadata_is_rehydrated_without_mutation(tmp_path):
    path = tmp_path / 'image.png'
    Image.new('RGB', (320, 320), 'blue').save(path)
    asset = store_path('image', path)
    try:
        for saved in [{'assetId': asset.id}, {'imageAsset': {'id': asset.id, 'url': 'https://bad.invalid'}}]:
            project = {'background': {'type': 'image', **saved}}
            restored = prepare_footage(project)['background']
            assert restored['imageAsset'] == asset.public()
            assert restored['assetId'] == asset.id and restored['url'] == asset.url
            assert project['background'] == {'type': 'image', **saved}
    finally:
        delete_asset(asset.id)


@pytest.mark.parametrize('kind', ['image', 'video'])
def test_missing_legacy_asset_fails_before_starting_browser(kind):
    with pytest.raises(ValueError, match='Import it again'):
        prepare_footage({'background': {'type': kind, 'assetId': 'missing'}})


def test_forced_ffmpeg_is_not_reported_as_a_codec_failure():
    assert 'flat text' in _fallback_reason({}, object())
    assert 'bitrate' in _fallback_reason({'export': {'bitrateMbps': 150}}, None)
    assert 'effects' in _fallback_reason({'background': {'effects': {'particles': 50}}}, None)
    assert 'spectrum' in _fallback_reason({'audioAssetId': 'audio', 'background': {'sceneWave': True}}, None)
    assert _fallback_reason({'background': {'textSpace': 'scene'}}, None) is None


def test_png_fallback_is_lossless_and_rejects_invalid_images():
    frames = []
    origin = 'http://127.0.0.1:5565'
    image = Image.new('RGBA', (2, 2), (32, 64, 128, 200))
    def png(im, fmt='PNG'):
        buffer = io.BytesIO(); im.save(buffer, format=fmt); return buffer.getvalue()
    with frame_bridge(origin, 2, 2, lambda data, index: frames.append((index, data))) as (url, state):
        def send(data, request_origin=origin):
            request = urllib.request.Request(url, data=data, headers={'Origin': request_origin, 'Content-Type': 'image/png'})
            return urllib.request.urlopen(request, timeout=3)
        for bad in [b'not a PNG', png(Image.new('RGBA', (3, 2))), png(image.convert('RGB'), 'JPEG')]:
            with pytest.raises(urllib.error.HTTPError) as error:
                send(bad)
            assert error.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as error:
            send(png(image), 'https://untrusted.invalid')
        assert error.value.code == 403
        with send(png(image)) as response:
            assert response.status == 204
        assert frames == [(0, image.tobytes())]
        assert state == {'frames': 1, 'error': None}


def test_audio_metadata_errors_compatibility_fallback_is_narrow(tmp_path, monkeypatch):
    whisper_audio = pytest.importorskip('faster_whisper.audio')
    import phrasync.media
    expected = np.ones(16000, dtype=np.float32)
    decoder = Mock(side_effect=TypeError("open() got an unexpected keyword argument 'metadata_errors'"))
    fallback = Mock(return_value=expected)
    monkeypatch.setattr(whisper_audio, 'decode_audio', decoder)
    monkeypatch.setattr(phrasync.media, 'decode_audio_mono', fallback)
    assert load_audio(tmp_path / 'tone.wav') is expected
    fallback.assert_called_once_with(tmp_path / 'tone.wav', sample_rate=16000)
    decoder.side_effect = TypeError('unrelated error')
    with pytest.raises(TypeError, match='unrelated'):
        load_audio(tmp_path / 'tone.wav')
    assert fallback.call_count == 1


def test_fixed_language_decode_recovers_pyav_mismatch(monkeypatch):
    import phrasync.transcribe as transcription
    audio = np.zeros(16000, dtype=np.float32)
    model = Mock()
    model.transcribe.side_effect = [TypeError("open() got an unexpected keyword argument 'metadata_errors'"),
                                   (iter([]), SimpleNamespace(language='en'))]
    monkeypatch.setattr(transcription, 'load_audio', lambda _: audio)
    result = transcription._decode_pass(model, 'audio.wav', {'language': 'en'})
    assert result['segments'] == []
    assert model.transcribe.call_args.args[0] is audio
    assert model.transcribe.call_args.kwargs == {'language': 'en'}


def test_real_audio_is_decoded_when_pyav_has_the_v19_signature(tmp_path, monkeypatch):
    av = pytest.importorskip('av')
    pytest.importorskip('faster_whisper.audio')
    path = tmp_path / 'compatibility.wav'
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1', str(path)])
    def incompatible_open(file, mode='r'):
        raise AssertionError('The incompatible keyword must be rejected before entering the decoder')
    monkeypatch.setattr(av, 'open', incompatible_open)
    audio = load_audio(path)
    assert audio.dtype == np.float32 and audio.size == 16000
    assert np.sqrt(np.mean(audio**2)) > .03


def test_spectrum_matches_web_audio_bins_range_and_timeline_history(tmp_path):
    path = tmp_path / 'tone.wav'
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'sine=frequency=938:sample_rate=48000:duration=4', str(path)])
    full = SpectrumSource(str(path), 60)
    ranged = SpectrumSource(str(path), 30, start_time=2.5)
    low_fps = SpectrumSource(str(path), 24)
    try:
        assert not any(full.read(0))  # no look-ahead into the first frame
        for index in range(151):
            reference = full.read(index)
        assert len(reference) == 128 and int(np.argmax(reference)) == 5
        assert ranged.read(0) == pytest.approx(reference, abs=1/255)
        for index in range(61):
            other = low_fps.read(index)
        assert other == reference  # same absolute time, independent of export FPS
        assert full.window.size == 256 and full.smoothed.size == 128
        assert all(0 <= value <= 1 for value in reference)
        assert np.allclose(np.array(reference)*255, np.floor(np.array(reference)*255 + 1e-8))
        assert full.read(150) == reference
    finally:
        for source in [full, ranged, low_fps]:
            source.close()


def test_preview_uses_the_same_spectrum_configuration():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'static/app-lyrics.js').read_text(encoding='utf-8')
    assert 'sampleRate: 48000' in source and 'fftSize = 256' in source
    assert 'smoothingTimeConstant = .78' in source
    assert 'minDecibels = -100' in source and 'maxDecibels = -30' in source
