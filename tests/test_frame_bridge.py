import urllib.request
import urllib.error
import pytest
from phrasync.frame_bridge import frame_bridge


def post(url, data, origin):
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers={'Origin': origin}), timeout=3)


def test_bridge_transfers_ordered_exact_frames_and_rejects_untrusted_input():
    frames = []
    origin = 'http://127.0.0.1:5526'
    with frame_bridge(origin, 2, 2, lambda data, index: frames.append((index, data))) as (url, state):
        for destination, data, request_origin, status in [
            (url, b'x'*16, 'https://evil.example', 403),
            (url + 'wrong', b'x'*16, origin, 403),
            (url, b'x'*17, origin, 400),
            (url, b'x'*15, origin, 400),
        ]:
            with pytest.raises(urllib.error.HTTPError) as error:
                post(destination, data, request_origin)
            assert error.value.code == status
        assert frames == []
        for value in [b'a'*16, b'b'*16]:
            with post(url, value, origin) as response:
                assert response.status == 204
        assert frames == [(0,b'a'*16),(1,b'b'*16)]
        assert state['frames'] == 2 and state['error'] is None


def test_bridge_reports_encoder_failure_without_counting_frame():
    def fail(*_):
        raise RuntimeError('encoder failed')
    with frame_bridge('http://localhost:5526', 1, 1, fail) as (url, state):
        with pytest.raises(urllib.error.HTTPError) as error:
            post(url, b'1234', 'http://localhost:5526')
        assert error.value.code == 500
        assert state == {'frames': 0, 'error': 'encoder failed'}
