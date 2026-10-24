import json
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
import pytest
from phrasync.hardware_encoding import nvenc_args, nvenc_available
from phrasync.frame_bridge import frame_bridge
from phrasync.footage_frames import PacketReader, footage_frame_bridge
from phrasync.storage import store_path, delete_asset
from phrasync.media import run_ffmpeg


def test_gpu_color_tags_do_not_change_cpu_colour_conversion():
    from phrasync.renderer import webgl_color_args
    assert 'matrix_coefficients=1' in webgl_color_args('h264-gpu')[1]
    assert 'transfer_characteristics=13' in webgl_color_args('h264-gpu')[1]
    assert webgl_color_args('h264') == []
    assert webgl_color_args('mp4') == []


def test_nvenc_preserves_custom_rate_and_quality_controls():
    args = nvenc_args({'export': {'bitrateMbps': 150}})
    assert args[args.index('-b:v')+1] == '150000000'
    assert '-x264-params' not in args and '-crf' not in args
    assert nvenc_args({'export': {'crf': 20}})[-3:] == ['20','-b:v','0']


def test_nvenc_probe_failure_is_cached_and_nonfatal(monkeypatch):
    nvenc_available.cache_clear()
    calls = []
    def fail(*a, **kw):
        calls.append(1)
        raise OSError('No NVIDIA device')
    monkeypatch.setattr('phrasync.hardware_encoding.subprocess.run', fail)
    assert not nvenc_available('missing-ffmpeg', 640, 360, 30)
    assert not nvenc_available('missing-ffmpeg', 640, 360, 30)
    assert len(calls) == 1
    nvenc_available.cache_clear()


def test_nvenc_failure_restarts_the_complete_pass_on_cpu(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from phrasync import webgl_renderer as renderer
    monkeypatch.setattr(renderer, 'can_use_nvenc', lambda *args: True)
    stream = Mock(side_effect=[renderer.HardwareEncoderError('Device lost'), None])
    monkeypatch.setattr(renderer, '_encode_canvas_stream', stream)
    devtools = Mock()
    renderer._encode_canvas_ffmpeg(devtools, {'__renderOrigin':'http://127.0.0.1:5568'}, tmp_path/'stream.mp4',
                                  width=320, height=180, fps=30, frame_count=20, envelope=[])
    assert [call.kwargs['hardware'] for call in stream.call_args_list] == [True, False]
    assert all(call.kwargs['frame_count'] == 20 for call in stream.call_args_list)
    assert devtools.evaluate.call_count == 1
    assert devtools.evaluate.call_args.args[0].startswith('VFExport.prepare(')


def test_encoded_bridge_accepts_bounded_chunks_not_arbitrary_origins():
    origin='http://127.0.0.1:5568'; data=[]
    with frame_bridge(origin, 4, 4, lambda b,i:data.append((i,b)), encoded=True) as (url,state):
        for b in [b'NAL-a',b'NAL-b-longer']:
            with urllib.request.urlopen(urllib.request.Request(url,data=b,headers={'Origin':origin})) as response:
                assert response.status == 204
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(url,data=b'evil',headers={'Origin':'https://evil.invalid'}))
        assert error.value.code == 403
        assert data == [(0,b'NAL-a'),(1,b'NAL-b-longer')] and state['frames'] == 2


def test_packet_bridge_is_private_bounded_and_seeks_to_keyframe(tmp_path):
    path=tmp_path/'source.mp4'
    run_ffmpeg(['-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=3',
                '-c:v','libx264','-g','48','-bf','2','-pix_fmt','yuv420p',str(path)])
    asset=store_path('video',path)
    origin='http://127.0.0.1:5568'
    try:
        reader=PacketReader(path,1.4)
        try:
            assert reader.config['codec'].startswith('avc1.')
            batch=reader.read()
            assert len(batch['packets']) == 8 and batch['packets'][0]['type'] == 'key'
            assert batch['packets'][0]['timestamp'] <= 1400000
        finally: reader.close()
        with footage_frame_bridge(origin,{'background':{'clips':[{'id':'a','asset':asset.public()}]}}) as url:
            def get(query, request_origin=origin):
                return urllib.request.urlopen(urllib.request.Request(url+query,headers={'Origin':request_origin}),timeout=5)
            for query,request_origin,status in [('?id=a&action=open', 'https://evil.invalid',403),
                    ('?id=../secret&action=open',origin,400),('?id=a&action=open&time=nan',origin,400)]:
                with pytest.raises(urllib.error.HTTPError) as error: get(query,request_origin)
                assert error.value.code == status
            with get('?id=a&action=open&time=1.4') as response: assert 'description' in json.load(response)
            with get('?id=a&action=read') as response: assert len(json.load(response)['packets']) == 8
    finally: delete_asset(asset.id)


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_preview_clock_corrects_old_drift_without_seek_storms():
    source=(Path(__file__).resolve().parents[1]/'static/media-effects.js').read_text(encoding='utf-8')
    script="""
const vm=require('node:vm'),assert=require('node:assert/strict');
const c={window:{}};vm.runInNewContext(SOURCE,c);
let seeks=0, clock=6.834;
const v={paused:false,seeking:false,playbackRate:1,pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()},
 get currentTime(){return clock},set currentTime(t){clock=t;seeks++}};
c.window.VFMedia.syncVideo(v,7,1,true);assert.equal(seeks,0);assert(v.playbackRate>1);
for(let i=1;i<=180;i++){clock+=v.playbackRate/60;c.window.VFMedia.syncVideo(v,7+i/60,1,true)}
assert(Math.abs(clock-10)<.008);assert.equal(seeks,0);
v.seeking=true;c.window.VFMedia.syncVideo(v,12,1,true);assert.equal(seeks,0);
v.seeking=false;clock=7;c.window.VFMedia.syncVideo(v,7.02,1,true);assert.equal(seeks,0);assert(v.playbackRate>1);
clock=7.03;c.window.VFMedia.syncVideo(v,7.02,1,true);assert(v.playbackRate<1);
c.window.VFMedia.syncVideo(v,2,.5,false);assert(v.paused);assert.equal(clock,2);assert.equal(v.playbackRate,.5);
""".replace('SOURCE',json.dumps(source))
    result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_gpu_video_frames_are_drawn_and_closed_not_silently_omitted():
    source=(Path(__file__).resolve().parents[1]/'static/media-effects.js').read_text(encoding='utf-8')
    script="""
const vm=require('node:vm'),assert=require('node:assert/strict');let drawn=0,closed=0,ready;
const frame={displayWidth:640,displayHeight:360,close(){closed++}};
const video={videoWidth:640,videoHeight:360,duration:3,muted:true,paused:true,
 addEventListener(name,cb){if(name==='loadeddata')ready=cb},set src(v){ready()},pause(){}};
const ctx={canvas:{width:320,height:180},save(){},restore(){},fillRect(){},translate(){},rotate(){},drawImage(s){assert.equal(s,frame);drawn++}};
const project={background:{footageEnabled:true,clips:[{id:'a',asset:{id:'video',kind:'video'},start:0,end:1,in:0,rate:1}],effects:{}}};
const c={window:{__vfFootageFramesEndpoint:'private',VFFootageDecoder:{frame:async()=>frame}},project,
 document:{createElement:()=>video},performance:{now:()=>0}};vm.runInNewContext(SOURCE,c);
(async()=>{await c.window.VFMedia.exportBase(ctx,.5,0);assert.equal(drawn,1);assert.equal(closed,1)})()
.catch(error=>{console.error(error);process.exitCode=1});
""".replace('SOURCE',json.dumps(source))
    result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr
