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


def test_idle_browser_preconnection_cannot_block_real_frame_upload():
    import socket
    from urllib.parse import urlparse
    origin = 'http://127.0.0.1:5526'
    frames = []
    with frame_bridge(origin, 1, 1, lambda data, index: frames.append((index, data))) as (url, state):
        address = urlparse(url)
        with socket.create_connection((address.hostname, address.port), timeout=2):
            with post(url, b'1234', origin) as response:
                assert response.status == 204
        assert frames == [(0, b'1234')] and state['frames'] == 1


def test_browser_can_reuse_one_connection_for_ordered_frames():
    import http.client
    from urllib.parse import urlparse
    origin = 'http://127.0.0.1:5526'
    frames = []
    with frame_bridge(origin, 1, 1, lambda data, index: frames.append((index, data))) as (url, state):
        address = urlparse(url)
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=3)
        try:
            local_port = None
            for i in range(20):
                connection.request('POST', address.path, body=bytes([i])*4, headers={'Origin': origin})
                response = connection.getresponse()
                assert response.status == 204 and not response.will_close
                response.read()
                if local_port is None: local_port = connection.sock.getsockname()[1]
                assert connection.sock.getsockname()[1] == local_port
            assert state['frames'] == 20
            assert [index for index, _ in frames] == list(range(20))
        finally:
            connection.close()


def test_old_serial_server_reproduces_preconnection_stall(monkeypatch):
    import socket
    import threading
    from http.server import HTTPServer
    from urllib.parse import urlparse
    import phrasync.frame_bridge as bridge_module
    # Negative control: the original single-threaded server must stall until
    # its idle first connection closes, even though the real upload is ready.
    monkeypatch.setattr(bridge_module, 'ThreadingHTTPServer', HTTPServer)
    origin = 'http://127.0.0.1:5526'
    done = threading.Event()
    outcome = []
    with frame_bridge(origin, 1, 1, lambda *_: None) as (url, state):
        address = urlparse(url)
        idle = socket.create_connection((address.hostname, address.port), timeout=2)
        idle.sendall(b'POST /')
        def upload():
            try:
                with post(url, b'1234', origin) as response: outcome.append(response.status)
            finally:
                done.set()
        thread = threading.Thread(target=upload)
        thread.start()
        try:
            assert not done.wait(.2)
            assert state['frames'] == 0
        finally:
            idle.close()
            thread.join(timeout=3)
        assert done.is_set() and outcome == [204] and state['frames'] == 1
