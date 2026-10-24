"""Private, bounded compressed-packet bridge for sequential GPU video decoding."""
from collections import OrderedDict
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import math
import secrets
import threading
from urllib.parse import urlparse, parse_qs
from .storage import get_asset


class PacketReader:
    def __init__(self, path, time):
        import av
        self.container = av.open(str(path))
        try:
            self.stream = self.container.streams.video[0]
            codec = self.stream.codec_context
            extra = codec.extradata
            if codec.name != 'h264' or not extra or extra[0] != 1:
                raise ValueError('Use browser codec compatibility path')
            frame = next(self.container.decode(self.stream))
            if (self.stream.metadata.get('rotate') or self.stream.sample_aspect_ratio not in (None, 1)
                    or any('DISPLAYMATRIX' in str(s.type) for s in frame.side_data)
                    or frame.format.name not in {'yuv420p', 'yuvj420p', 'nv12'}):
                raise ValueError('Use browser colour/orientation conversion')
            self.config = {'codec': 'avc1.' + extra[1:4].hex(), 'codedWidth': codec.width,
                           'codedHeight': codec.height, 'description': base64.b64encode(extra).decode()}
            self.container.seek(int(time/self.stream.time_base), stream=self.stream)
            self.iterator = iter(self.container.demux(self.stream))
            self.eof = False
        except Exception:
            self.container.close()
            raise

    def read(self):
        packets = []
        while len(packets) < 8:
            packet = next(self.iterator, None)
            if packet is None:
                self.eof = True
                break
            if packet.pts is None or not packet.size:
                continue
            packets.append({'timestamp': round(packet.pts * packet.time_base * 1000000),
                'duration': max(1, round(packet.duration * packet.time_base * 1000000)),
                'type': 'key' if packet.is_keyframe else 'delta',
                'data': base64.b64encode(bytes(packet)).decode()})
        return {'packets': packets, 'eof': self.eof}

    def close(self): self.container.close()


@contextmanager
def footage_frame_bridge(origin, project):
    token = secrets.token_urlsafe(32)
    assets = {}
    bg = project.get('background') or {}
    for clip in bg.get('clips') or []:
        asset = clip.get('asset') or {}
        if asset.get('kind') == 'video': assets[str(clip['id'])] = asset.get('id')
    if bg.get('type') == 'video':
        assets['__legacy'] = bg.get('assetId') or (bg.get('videoAsset') or {}).get('id')
    readers = OrderedDict()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        disable_nagle_algorithm = True
        def log_message(self, *args): pass
        def setup(self):
            super().setup(); self.connection.settimeout(30)
        def handle(self):
            try: super().handle()
            except (ConnectionResetError, BrokenPipeError, TimeoutError): pass
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != '/'+token or self.headers.get('Origin') != origin:
                self.reply(403); return
            params = parse_qs(parsed.query)
            try:
                key, action = params['id'][0], params['action'][0]
                time = float(params.get('time', ['0'])[0])
                if key not in assets or action not in {'open','read'} or not math.isfinite(time) or not 0 <= time <= 86400:
                    raise ValueError('Invalid request')
            except (ValueError, KeyError, IndexError):
                self.reply(400); return
            with lock:
                try:
                    if action == 'open':
                        old = readers.pop(key, None)
                        if old: old.close()
                        asset = get_asset(assets[key], 'video')
                        if not asset: raise ValueError('Missing footage asset')
                        readers[key] = PacketReader(asset.path, time)
                        while len(readers) > 8: readers.popitem(last=False)[1].close()
                        result = readers[key].config
                    else:
                        reader = readers.pop(key); readers[key] = reader
                        result = reader.read()
                except Exception:
                    old = readers.pop(key, None)
                    if old: old.close()
                    self.reply(204); return
                self.reply(200, json.dumps(result).encode())
        def reply(self, status, data=b''):
            self.send_response(status)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if data: self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}/{token}'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        with lock:
            for reader in readers.values(): reader.close()
