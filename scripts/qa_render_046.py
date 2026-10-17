"""Local real-export regression matrix and repeatable 1080p benchmark."""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phrasync.media import run_ffmpeg, decode_test, probe_duration
from phrasync.qa import preflight_project
from phrasync.renderer import render_project
from phrasync.storage import store_path, delete_asset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin', default='http://127.0.0.1:5526')
    parser.add_argument('--label', default='after')
    parser.add_argument('--benchmark-only', action='store_true')
    parser.add_argument('--seconds', type=float, default=3)
    parser.add_argument('--rates-only', action='store_true')
    parser.add_argument('--api', action='store_true', help='Run jobs through the packaged server instead of source imports')
    args = parser.parse_args()
    root = Path('qa_out/render-046')
    root.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.new('RGB', (640, 360), '#502068').save(root / 'source.png')
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=3',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(root / 'source.mp4')], check=True)
    run_ffmpeg(['-y', '-f', 'lavfi', '-i', f'sine=frequency=440:duration={max(3,args.seconds)}', str(root / 'audio.wav')], check=True)
    assets = [store_path(kind, root / filename) for kind, filename in
              [('image', 'source.png'), ('video', 'source.mp4'), ('audio', 'audio.wav')]]
    image, video, audio = assets
    base = {'duration': 3, 'audioAssetId': audio.id, '__renderOrigin': args.origin,
            'canvas': {'width': 1920, 'height': 1080, 'fps': 30},
            'background': {'type': 'dynamic', 'visual': 'aurora', 'textSpace': 'flat',
                           'effects': {'gradient': 25, 'particles': 20, 'spectrum': 30, 'shake': 1, 'bpm': 120}},
            'style': {'fontPreset': 'modern', 'fontSize': 100, 'preset': 'spiral-flight'},
            'cues': [{'id': 'a', 'start': 0, 'end': 3, 'text': 'EXPORT TEST 日本語'}],
            'exportRange': {'in': .5, 'out': 2.5}, 'export': {'preset': 'medium', 'crf': 20}}
    results = []
    try:
        cases = [('1080p-effects-flat', copy.deepcopy(base))]
        if args.benchmark_only and args.seconds != 3:
            cases[0][1]['duration'] = args.seconds
            cases[0][1]['exportRange'] = {'in': 0, 'out': args.seconds}
        if args.rates_only:
            cases = []
            for fps in [12, 23, 24, 25, 30, 50, 60]:
                p = copy.deepcopy(base)
                p['canvas'] = {'width':320,'height':320,'fps':fps}
                p['exportRange'] = {'in':1,'out':2}
                p['export']['preset'] = 'ultrafast'
                p['background'].update(visual='scene3d',sceneKit='ocean',textSpace='scene')
                cases.append((f'fps-{fps}',p))
        elif not args.benchmark_only:
            for bg_type in ['dynamic', 'image', 'video']:
                for text_space in ['flat', 'scene']:
                    for ranged in [False, True]:
                        p = copy.deepcopy(base)
                        p['canvas'] = {'width': 640, 'height': 360, 'fps': 30}
                        p['export']['preset'] = 'ultrafast'
                        p['background'].update(type=bg_type, assetId=video.id if bg_type == 'video' else image.id,
                                               textSpace=text_space, footageEnabled=True, tracks=['V1','V2','V3'])
                        p['background']['clips'] = [
                            {'id':'video', 'track':0, 'asset':video.public(), 'start':0, 'end':3},
                            {'id':'image', 'track':1, 'asset':image.public(), 'start':.5, 'end':2.5, 'opacity':.3,
                             'transition':'fade', 'fadeIn':.2, 'fadeOut':.2},
                            {'id':'visual', 'track':2, 'asset':{'kind':'visual', 'settings':{'visual':'scene3d','sceneKit':'ocean'}},
                             'start':1, 'end':2, 'opacity':.5, 'transition':'wipe', 'fadeIn':.2}]
                        if not ranged:
                            p.pop('exportRange')
                        cases.append((f'{bg_type}-{text_space}-{ranged}',p))
        for name, p in cases:
            report = preflight_project(p)
            assert report.ok, report.public()
            output = root / f'{args.label}-{name}.mp4'
            if args.api:
                import urllib.request
                import time
                def call(path, payload=None):
                    data = json.dumps(payload).encode() if payload is not None else None
                    with urllib.request.urlopen(urllib.request.Request(args.origin+path,data=data,
                            headers={'Content-Type':'application/json'}),timeout=30) as response:
                        return json.load(response)
                assert call('/api/health')['version'] == '0.4.6'
                job = call('/api/render', {'project':p,'title':f'{args.label}-{name}', 'outputDirectory':str(root.resolve())})
                deadline = time.monotonic()+180
                while job['state'] not in {'complete','failed','cancelled'} and time.monotonic()<deadline:
                    time.sleep(.3)
                    job = call('/api/render/'+job['id'])
                assert job['state'] == 'complete', job
                assert job['postflight']['ok'], job
                result = job['result']
                output = Path(result['path'])
            else:
                result = render_project(p, output)
            assert decode_test(output)[0], name
            assert abs(probe_duration(output) - result['duration']) < .1
            assert result['frames'] == round(result['duration'] * p['canvas']['fps'])
            decoded = run_ffmpeg(['-i',str(output),'-map','0:v:0','-f','null','-'], check=True)
            import re
            counts = re.findall(rb'frame=\s*(\d+)', decoded.stderr)
            assert counts and int(counts[-1]) == result['frames'], decoded.stderr[-1000:]
            frame = run_ffmpeg(['-i', str(output), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'], check=True)
            import io
            pixels = Image.open(io.BytesIO(frame.stdout)).convert('RGB')
            assert pixels.size == (result['width'], result['height'])
            assert max(pixels.resize((64,36)).getextrema()[0]) > 20, 'Black export frame'
            pixels.thumbnail((960,540))
            pixels.save(root / f'{args.label}-{name}.png')
            results.append({'case': name, **result})
            print(json.dumps(results[-1]), flush=True)
        (root / f'{args.label}-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    finally:
        for asset in assets:
            delete_asset(asset.id)


if __name__ == '__main__':
    main()
