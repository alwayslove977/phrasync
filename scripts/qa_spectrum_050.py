"""Compare the offline FFT math against Chromium's real Web Audio analyser."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from phrasync.webgl_renderer import _browser_path, _free_port, _target_socket, _DevTools
from phrasync.processes import background_flags


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='phrasync-spectrum-qa-') as folder:
        port = _free_port()
        process = subprocess.Popen([str(_browser_path()), '--headless=new', '--mute-audio',
            f'--remote-debugging-port={port}', '--remote-allow-origins=*', f'--user-data-dir={folder}', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=background_flags())
        devtools = None
        try:
            devtools = _DevTools(_target_socket(port), port)
            for smoothing in [0, .78]:
                actual = devtools.evaluate("""(async()=>{
                  const ctx = new OfflineAudioContext(1,48000,48000);
                  const buffer = ctx.createBuffer(1,48000,48000), data=buffer.getChannelData(0);
                  for(let i=0;i<data.length;i++)data[i]=.125*Math.sin(2*Math.PI*938*i/48000);
                  const source=ctx.createBufferSource();source.buffer=buffer;
                  const analyser=ctx.createAnalyser();analyser.fftSize=256;
                  analyser.smoothingTimeConstant=SMOOTHING;analyser.minDecibels=-100;analyser.maxDecibels=-30;
                  source.connect(analyser);analyser.connect(ctx.destination);source.start();
                  const suspended=ctx.suspend(.5), finished=ctx.startRendering();await suspended;
                  const samples=new Float32Array(256),bins=new Uint8Array(128);
                  analyser.getFloatTimeDomainData(samples);analyser.getByteFrequencyData(bins);
                  await ctx.resume();await finished;
                  return {samples:Array.from(samples),bins:Array.from(bins)};
                })()""".replace('SMOOTHING', str(smoothing)))
                n = np.arange(256) / 256
                window = .42 - .5*np.cos(2*np.pi*n) + .08*np.cos(4*np.pi*n)
                magnitude = np.abs(np.fft.rfft(np.array(actual['samples']) * window))[:128]/256
                magnitude *= 1-smoothing
                expected = np.floor(np.clip((20*np.log10(np.maximum(magnitude,1e-30))+100)/70,0,1)*255)
                difference = np.abs(expected-np.array(actual['bins']))
                assert difference.max() <= 1, {'maxByteError': float(difference.max()), 'smoothing': smoothing}
                results.append({'smoothing': smoothing, 'maxByteError': float(difference.max()),
                                'peakBin': int(np.argmax(actual['bins']))})
        finally:
            if devtools: devtools.close()
            process.terminate(); process.wait(timeout=10)
    root = Path(__file__).resolve().parents[1] / 'qa_out/render-050'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'web-audio-parity.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
