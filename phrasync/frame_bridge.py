"""One-frame-at-a-time, authenticated loopback transport to the video encoder."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import threading


@contextmanager
def frame_bridge(origin, width, height, consume):
    token = secrets.token_urlsafe(32)
    frame_size = width * height * 4
    state = {"frames": 0, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            return self.path == '/' + token and self.headers.get('Origin') == origin

        def respond(self, status):
            # Drain small rejected bodies before closing, avoiding a Windows
            # TCP reset that can hide the HTTP error. Never read an unbounded body.
            if status in {400, 403} and self.command == 'POST':
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if 0 < size <= frame_size + 1:
                        self.connection.settimeout(2)
                        self.rfile.read(size)
                except (ValueError, OSError):
                    pass
            self.send_response(status)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_OPTIONS(self):
            self.respond(204 if self.allowed() else 403)

        def do_POST(self):
            if not self.allowed():
                self.respond(403)
                return
            try:
                if int(self.headers.get('Content-Length', '0')) != frame_size:
                    self.respond(400)
                    return
                self.connection.settimeout(30)
                data = self.rfile.read(frame_size)
                if len(data) != frame_size:
                    raise RuntimeError('Incomplete canvas frame')
                consume(data, state['frames'])
                state['frames'] += 1
                self.respond(204)
            except Exception as exc:
                state['error'] = str(exc)
                self.respond(500)

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/{token}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
