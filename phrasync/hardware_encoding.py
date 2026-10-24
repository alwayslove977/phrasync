"""Probe the actual encoder, not just its presence in FFmpeg's build."""
from functools import lru_cache
import subprocess

from .encoding import bitrate_bps
from .media import ffmpeg_exe
from .processes import background_flags


@lru_cache(maxsize=32)
def nvenc_available(executable, width, height, fps):
    try:
        result = subprocess.run([
            executable, '-v', 'error', '-f', 'lavfi', '-i',
            f'color=size={width}x{height}:rate={fps}', '-frames:v', '1',
            '-an', '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p',
            '-f', 'null', '-'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=8, creationflags=background_flags())
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def nvenc_args(project):
    rate = bitrate_bps(project)
    args = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'hq', '-profile:v', 'high']
    if rate is not None:
        return args + ['-rc', 'cbr', '-b:v', str(rate), '-minrate', str(rate),
                       '-maxrate', str(rate), '-bufsize', str(rate)]
    return args + ['-rc', 'vbr', '-cq', str(project.get('export', {}).get('crf', 18)), '-b:v', '0']


def can_use_nvenc(width, height, fps):
    return nvenc_available(ffmpeg_exe(), width, height, fps)
