"""Real local export matrix for issue #5; no publishing or Store operations."""
import argparse
import copy
import io
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from phrasync.media import run_ffmpeg, decode_test, probe_duration
from phrasync.renderer import render_project
from phrasync.storage import store_path, delete_asset
from phrasync import webgl_renderer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin', default='http://127.0.0.1:5565')
    parser.add_argument('--label', default='source')
    parser.add_argument('--api', action='store_true')
    parser.add_argument('--group', choices=['all', 'core', 'extended'], default='all')
    parser.add_argument('--retry-failed', action='store_true', help='Keep passing results and rerun failed/new cases')
    parser.add_argument('--long', action='store_true', help='Also exercise a synthetic 270-second spectrum/particles project')
    parser.add_argument('--case', action='append', help='Run only the named case; may be repeated')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'qa_out/render-050'
    root.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (640, 360), '#503880').save(root / 'source.png')
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=60:duration=4',
                '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(root / 'source.mp4')])
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'sine=frequency=938:sample_rate=48000:duration=12', str(root / 'audio.wav')])
    assets = [store_path(kind, root / name) for kind, name in
              [('image', 'source.png'), ('video', 'source.mp4'), ('audio', 'audio.wav')]]
    image, video, audio = assets
    fx = {'particles': 30, 'spectrum': 70, 'gradient': 25, 'bw': 70, 'shake': 1,
          'pendulum': 2, 'flash': 15, 'drop': 8, 'pulse': 10, 'bpm': 120}
    base = {'title': 'Phrasync 0.5.0 QA', 'duration': 1, 'timelineDuration': 1,
            'audioAssetId': audio.id, '__renderOrigin': args.origin,
            'canvas': {'width': 640, 'height': 360, 'fps': 30},
            'background': {'type': 'dynamic', 'visual': 'aurora', 'textSpace': 'flat', 'shade': .15},
            'style': {'fontPreset': 'modern', 'fontSize': 85, 'preset': 'wipe-fill'},
            'cues': [{'id': 'a', 'start': 0, 'end': 1, 'text': 'EXPORT 日本語 中文'}],
            'export': {'preset': 'ultrafast', 'crf': 23}}
    cases = []
    def add(name, bg=None, *, effects=False, scene=False, ranged=False, **kwargs):
        p = copy.deepcopy(base)
        p['background'].update(copy.deepcopy(bg or {}))
        p['background']['textSpace'] = 'scene' if scene else 'flat'
        if effects: p['background']['effects'] = dict(fx)
        if ranged: p['exportRange'] = {'in': .2, 'out': .8}
        for key, value in kwargs.items(): p[key] = copy.deepcopy(value)
        cases.append((name, p))
    if args.group in ['all', 'core']:
        for kind in ['dynamic', 'image', 'video']:
            for scene in [False, True]:
                for effects in [False, True]:
                    for ranged in [False, True]:
                        bg = {'type': kind}
                        # Intentionally only assetId: legacy/source shape must work.
                        if kind != 'dynamic': bg['assetId'] = (image if kind == 'image' else video).id
                        add(f'{kind}-{"3d" if scene else "2d"}-fx{int(effects)}-range{int(ranged)}',
                            bg, scene=scene, effects=effects, ranged=ranged)
        for scene in [False, True]:
            for ranged in [False, True]:
                for transition in ['cut', 'fade', 'wipe', 'slide']:
                    bg = {'footageEnabled': True, 'tracks': ['V1','V2','V3','V4'], 'clips': [
                        {'id': 'video', 'asset': video.public(), 'track': 0, 'start': 0, 'end': 1, 'in': .3, 'rate': 1.5},
                        {'id': 'image', 'asset': image.public(), 'track': 1, 'start': 0, 'end': 1, 'opacity': .4,
                         'transition': transition, 'fadeIn': .2, 'fadeOut': .2, 'zoomEnd': 1.3, 'xEnd': .5},
                        {'id': 'visual', 'asset': {'id': 'ocean', 'kind': 'visual',
                            'settings': {'visual': 'scene3d', 'sceneKit': 'ocean'}},
                         'track': 2, 'start': .1, 'end': .9, 'opacity': .3, 'transition': transition, 'fadeIn': .2},
                        {'id': 'equalizer', 'asset': {'id': 'equalizer', 'kind': 'visual',
                            'settings': {'visual': 'equalizer'}}, 'track': 3, 'start': 0, 'end': 1, 'opacity': .2}]}
                    add(f'footage-{"3d" if scene else "2d"}-{transition}-range{int(ranged)}', bg,
                        scene=scene, effects=True, ranged=ranged)
    if args.group in ['all', 'extended']:
        for visual in ['particles', 'equalizer', 'grid', 'scene', 'scene3d']:
            add('visual-' + visual, {'visual': visual, 'sceneKit': 'ocean', 'sceneWave': True}, effects=True, scene=True)
        for fps in [12, 23, 24, 25, 30, 50, 60]:
            add(f'fps-{fps}', {'visual': 'scene3d', 'sceneKit': 'ocean'}, effects=True, scene=True, ranged=True,
                canvas={'width': 640, 'height': 360, 'fps': fps})
        for fps in [24, 30, 60]:
            for scene in [False, True]:
                add(f'4k-{fps}-{"3d" if scene else "2d"}', {'type': 'video', 'assetId': video.id},
                    effects=True, scene=scene, canvas={'width': 3840, 'height': 2160, 'fps': fps},
                    exportRange={'in': .4, 'out': .5}, export={'preset': 'ultrafast', 'bitrateMbps': 150})
        for fps in [30, 60]:
            add(f'1080p-{fps}', {'type': 'image', 'assetId': image.id}, effects=True,
                canvas={'width': 1920, 'height': 1080, 'fps': fps})
        add('1080p-10seconds', {'type': 'image', 'assetId': image.id, 'effects': {'particles': 30, 'spectrum': 60}},
            timelineDuration=10, canvas={'width': 1920, 'height': 1080, 'fps': 30})
        add('portrait-3d', {'visual': 'scene3d', 'sceneKit': 'ocean'}, effects=True, scene=True,
            canvas={'width': 360, 'height': 640, 'fps': 30})
        no_audio = copy.deepcopy(cases[-1][1]); no_audio.pop('audioAssetId'); cases.append(('no-audio', no_audio))
        add('4k-world-webcodecs', {'visual': 'scene3d', 'sceneKit': 'ocean'}, scene=True,
            canvas={'width': 3840, 'height': 2160, 'fps': 30}, exportRange={'in': .4, 'out': .5})
        for fps in [12, 30, 60]:
            add(f'single-frame-{fps}', canvas={'width': 640, 'height': 360, 'fps': fps},
                exportRange={'in': .4, 'out': .4 + 1/fps})
        if args.long:
            run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'sine=frequency=938:sample_rate=48000:duration=270', str(root / 'long-audio.wav')])
            long_audio = store_path('audio', root / 'long-audio.wav'); assets.append(long_audio)
            add('270seconds-spectrum-particles', {'type': 'image', 'assetId': image.id,
                'effects': {'particles': 30, 'spectrum': 60}}, timelineDuration=270, audioAssetId=long_audio.id,
                canvas={'width': 320, 'height': 320, 'fps': 30})
        if not args.api:
            add('forced-png-recovery', {'type': 'image', 'assetId': image.id}, effects=True)
            if args.group == 'all':
                recovery = copy.deepcopy(next(p for name, p in cases if name == 'footage-3d-fade-range1'))
                cases.append(('forced-png-footage-3d', recovery))
                cases.append(('forced-gpu-recovery', copy.deepcopy(recovery)))

    if args.case:
        cases = [(name, p) for name, p in cases if name in args.case]
        assert len(cases) == len(set(args.case)), 'Unknown or unavailable requested case'
    original_evaluate = webgl_renderer._DevTools.evaluate
    original_init = webgl_renderer._DevTools.__init__
    transport_stats = {}
    network_errors = []
    current = None
    def audited_init(self, *init_args, **init_kwargs):
        original_init(self, *init_args, **init_kwargs)
        if current != '270seconds-spectrum-particles': return
        socket = self.socket
        class AuditedSocket:
            def __getattr__(self, name): return getattr(socket, name)
            def recv(self, *recv_args, **recv_kwargs):
                value = socket.recv(*recv_args, **recv_kwargs)
                event = json.loads(value)
                if event.get('method') == 'Network.loadingFailed':
                    network_errors.append(event['params'])
                return value
        self.socket = AuditedSocket()
        self.call('Network.enable')
    def audited_evaluate(self, expression, **kwargs):
        if expression.startswith('VFGPUEncoder.prepare') and current.startswith('forced-png'):
            return False
        if current == 'forced-gpu-recovery' and expression.startswith('VFGPUEncoder.batch'):
            if transport_stats.get('gpu-batch-complete'):
                raise RuntimeError('QA simulated GPU failure after a completed batch')
            result = original_evaluate(self, expression, **kwargs)
            transport_stats['gpu-batch-complete'] = True
            return result
        if 'VFFrameTransport.send' in expression and current.startswith('forced-png'):
            original_evaluate(self, "CanvasRenderingContext2D.prototype.getImageData = function(){throw new Error('QA simulated pixel readback failure')};true")
        result = original_evaluate(self, expression, **kwargs)
        if 'VFFrameTransport.send' in expression and isinstance(result, dict):
            transport_stats[current] = result
        return result
    webgl_renderer._DevTools.evaluate = audited_evaluate
    webgl_renderer._DevTools.__init__ = audited_init
    results = []
    result_path = root / f'{args.label}-results.json'
    if args.retry_failed and result_path.exists():
        results = json.loads(result_path.read_text(encoding='utf-8'))
        if args.case:
            results = [row for row in results if row['case'] not in args.case]
        completed = {row['case'] for row in results if row['ok']}
        cases = [(name, p) for name, p in cases if name not in completed]
    def api(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(args.origin + path, data=data,
            headers={'Content-Type': 'application/json', 'Origin': args.origin})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    try:
        if args.api: assert api('/api/health')['version'] == '0.5.0'
        for name, p in cases:
            current = name
            output = root / f'{args.label}-{name}.mp4'
            started = time.monotonic()
            try:
                if args.api:
                    job = api('/api/render', {'project': p, 'title': f'{args.label}-{name}', 'outputDirectory': str(root)})
                    deadline = time.monotonic() + 300
                    while job['state'] not in {'complete','failed','cancelled'} and time.monotonic() < deadline:
                        time.sleep(.3); job = api('/api/render/' + job['id'])
                    assert job['state'] == 'complete', job
                    assert job['postflight']['ok'], job
                    result = job['result']; output = Path(result['path'])
                else:
                    result = render_project(p, output)
                assert decode_test(output)[0], name
                assert abs(probe_duration(output) - result['duration']) < .12
                assert result['frames'] == math.ceil(result['duration'] * p['canvas']['fps'] - 1e-9)
                decoded = run_ffmpeg(['-i', str(output), '-map', '0:v:0', '-f', 'null', '-'])
                counts = re.findall(rb'frame=\s*(\d+)', decoded.stderr)
                assert counts and int(counts[-1]) == result['frames'], f"Decoded {int(counts[-1]) if counts else 'unknown'} frames; expected {result['frames']}"
                import av
                with av.open(str(output)) as container:
                    stream = container.streams.video[0]
                    assert float(stream.average_rate) == p['canvas']['fps'], f"Reported framerate {stream.average_rate}; expected {p['canvas']['fps']}"
                    assert stream.width == p['canvas']['width'] and stream.height == p['canvas']['height']
                frame = run_ffmpeg(['-i', str(output), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'])
                pixels = Image.open(io.BytesIO(frame.stdout)).convert('RGB')
                assert max(pixels.resize((64, 36)).getextrema()[0]) > 20, 'Black export frame'
                pixels.thumbnail((480, 270)); pixels.save(root / f'{args.label}-{name}.png')
                transport = transport_stats.get(name)
                if name.startswith('forced-png'): assert transport['mode'] == 'png'
                elif transport: assert transport['mode'] == 'raw', transport
                row = {'case': name, 'ok': True, **result, 'transport': transport}
            except Exception as error:
                row = {'case': name, 'ok': False, 'error': str(error), 'networkErrors': network_errors[-5:]}
            row['wallSeconds'] = round(time.monotonic() - started, 3)
            previous_index = next((i for i, previous in enumerate(results) if previous['case'] == name), None)
            if previous_index is None: results.append(row)
            else: results[previous_index] = row
            print(json.dumps(row), flush=True)
            result_path.write_text(json.dumps(results, indent=2), encoding='utf-8')
    finally:
        webgl_renderer._DevTools.evaluate = original_evaluate
        webgl_renderer._DevTools.__init__ = original_init
        for asset in assets: delete_asset(asset.id)
    assert all(row['ok'] for row in results), [row for row in results if not row['ok']]


if __name__ == '__main__':
    main()
