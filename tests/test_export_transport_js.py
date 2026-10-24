"""Exercise transport recovery without depending on a particular GPU driver."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for browser-helper unit tests')
def test_raw_png_and_encoder_failure_do_not_duplicate_frames():
    source = (Path(__file__).resolve().parents[1] / 'static/export-transport.js').read_text(encoding='utf-8')
    script = """
const vm = require('node:vm'), assert = require('node:assert/strict');
function fixture() {
  const stats = {read:0, png:0, posts:0}, flags = {failRead:false, status:204, nullBlob:false};
  const scratch = {width:2,height:2,getContext:()=>({clearRect(){},drawImage(){},getImageData(){
    stats.read++; if(flags.failRead)throw new Error('GPU readback unavailable');
    return {data:new Uint8ClampedArray(16)};
  }})};
  const context = {window:{}, document:{createElement:()=>scratch}, fetch:async(_,request)=>{
    stats.posts++; assert(request.body); return {ok:flags.status===204,status:flags.status};
  }};
  vm.runInNewContext(SOURCE, context);
  const canvas = {width:2,height:2,toBlob(callback){stats.png++; callback(flags.nullBlob?null:new Uint8Array(16));}};
  return {send:()=>context.window.VFFrameTransport.send(canvas,'http://local/frame'),stats,flags};
}
(async()=>{
  const f=fixture(); assert.equal((await f.send()).mode,'raw');
  f.flags.failRead=true;
  assert.equal((await f.send()).mode,'png'); assert.equal((await f.send()).mode,'png');
  assert.equal(f.stats.posts,3); assert.equal(f.stats.read,2); assert.equal(f.stats.png,2);
  const failed=fixture(); failed.flags.status=503;
  await assert.rejects(failed.send(),/503/); assert.equal(failed.stats.posts,1); assert.equal(failed.stats.png,0);
  const empty=fixture(); empty.flags.failRead=true; empty.flags.nullBlob=true;
  await assert.rejects(empty.send(),/PNG encoding failed/); assert.equal(empty.stats.posts,0);
})().catch(error=>{console.error(error);process.exitCode=1});
""".replace('SOURCE', json.dumps(source))
    result = subprocess.run([shutil.which('node'), '-'], input=script, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
