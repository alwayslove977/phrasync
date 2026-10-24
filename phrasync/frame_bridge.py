"""One-frame-at-a-time, authenticated loopback transport to the video encoder."""
from contextlib import contextmanager
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
from PIL import Image, UnidentifiedImageError


@contextmanager
def frame_bridge(origin, width, height, consume, *, encoded=False):
    token = secrets.token_urlsafe(32)
    frame_size = width * height * 4
    max_png_size = max(1024, frame_size * 2)
    state = {"frames": 0, "error": None}
    consume_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        disable_nagle_algorithm = True

        def setup(self):
            super().setup()
            # Browsers can preconnect an idle socket before the next request.
            self.connection.settimeout(30)

        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError):
                # Chromium may reset an idle keep-alive socket on exit. Frame
                # read/consume errors are recorded separately by do_POST.
                pass

        def log_message(self, *args):
            pass

        def allowed(self):
            return self.path == '/' + token and self.headers.get('Origin') == origin

        def respond(self, status, *, drain=True):
            # Drain small rejected bodies before closing, avoiding a Windows
            # TCP reset that can hide the HTTP error. Never read an unbounded body.
            if drain and status in {400, 403} and self.command == 'POST':
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if 0 < size <= frame_size + 1:
                        self.connection.settimeout(2)
                        self.rfile.read(size)
                except (ValueError, OSError):
                    pass
            self.send_response(status)
            if status >= 400:
                self.close_connection = True
                self.send_header('Connection', 'close')
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Access-Control-Max-Age', '600')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_OPTIONS(self):
            self.respond(204 if self.allowed() else 403)

        def do_POST(self):
            if not self.allowed():
                self.respond(403)
                return
            try:
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    self.respond(400)
                    return
                png = self.headers.get('Content-Type', '').split(';')[0].strip().lower() == 'image/png'
                valid_size = 0 < size <= max_png_size if (png or encoded) else size == frame_size
                if not valid_size or (encoded and png):
                    self.respond(400)
                    return
                self.connection.settimeout(30)
                data = self.rfile.read(size)
                if len(data) != size:
                    raise RuntimeError('Incomplete canvas frame')
                if png:
                    try:
                        with Image.open(io.BytesIO(data)) as image:
                            if image.format != 'PNG' or image.size != (width, height) or getattr(image, 'n_frames', 1) != 1:
                                raise ValueError('Invalid canvas PNG dimensions or format')
                            data = image.convert('RGBA').tobytes()
                    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
                        self.respond(400, drain=False)
                        return
                with consume_lock:
                    if state['error']:
                        self.respond(500)
                        return
                    try:
                        consume(data, state['frames'])
                    except Exception as exc:
                        state['error'] = str(exc)
                        raise
                    state['frames'] += 1
                self.respond(204)
            except Exception as exc:
                state['error'] = str(exc)
                self.respond(500)

    # A single-threaded HTTPServer can block on Chromium's idle preconnection
    # while the real frame upload waits on another connection. Keep-alive also
    # avoids thousands of TCP handshakes during a long export.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/{token}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
