"""Exercise the software-graphics fallback without changing application defaults."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phrasync import webgl_renderer
from phrasync.renderer import render_project
from phrasync.media import decode_test, run_ffmpeg

original = webgl_renderer.subprocess.Popen
def software_browser(command, *args, **kwargs):
    if '--headless=new' in command:
        command = [*command, '--use-angle=swiftshader']
    return original(command, *args, **kwargs)

project = {'duration':1,'exportRange':{'in':.5,'out':1},'__renderOrigin':'http://127.0.0.1:5526',
           'canvas':{'width':320,'height':320,'fps':24},
           'background':{'type':'dynamic','visual':'scene3d','sceneKit':'ocean','textSpace':'scene'},
           'style':{'fontPreset':'modern','fontSize':50,'preset':'spiral-flight'},
           'cues':[{'id':'a','start':0,'end':1,'text':'SOFTWARE FALLBACK'}],
           'export':{'preset':'ultrafast'}}
try:
    webgl_renderer.subprocess.Popen = software_browser
    output = Path('qa_out/render-046/software-fallback.mp4')
    result = render_project(project,output)
    assert result['frames'] == 12 and decode_test(output)[0]
    print('PASS software graphics fallback',result,flush=True)
finally:
    webgl_renderer.subprocess.Popen = original
print(run_ffmpeg(['-hide_banner','-i','qa_out/render-046/final-rates-fps-23.mp4'],check=False).stderr.decode(),flush=True)
