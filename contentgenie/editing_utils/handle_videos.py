import os
import random
import contextlib
import io
import yt_dlp
import subprocess
import json

from moviepy import VideoFileClip

from contentgenie.config.performance import (
    get_background_clip_encode_args,
    get_bool_setting,
    get_ffmpeg_binary,
    nvenc_runtime_available,
)


def _get_ffmpeg_binary():
    return get_ffmpeg_binary()


def _validate_video_clip(video_path, expected_duration=None):
    if not os.path.exists(video_path):
        raise Exception("Random clip failed to be written")
    if os.path.getsize(video_path) < 1024 * 1024:
        raise Exception(f"Random clip is invalid or too small: {os.path.getsize(video_path)} bytes")

    with contextlib.redirect_stdout(io.StringIO()):
        clip = VideoFileClip(video_path)
    try:
        if not clip.duration:
            raise Exception("Random clip has no readable duration")
        if expected_duration and clip.duration < expected_duration - 1:
            raise Exception(f"Random clip is too short: {clip.duration}s")
    finally:
        clip.close()

def getYoutubeVideoLink(url):
    format_filter = "[height<=1920]" if 'shorts' in url else "[height<=1080]"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "no_call_home": True,
        "no_check_certificate": True,
        # Look for m3u8 formats first, then fall back to regular formats
        "format": f"bestvideo[ext=m3u8]{format_filter}/bestvideo{format_filter}"
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            dictMeta = ydl.extract_info(
                url,
                download=False)
            return dictMeta['url'], dictMeta['duration']
    except Exception as e:
        raise Exception(f"Failed getting video link from the following video/url {url} {e.args[0]}")

def extract_random_clip_from_video(video_url, video_duration, clip_duration, output_file):
    """Extracts a clip from a video using a signed URL.
    Args:
        video_url (str): The signed URL of the video.
        video_url (int): Duration of the video.
        start_time (int): The start time of the clip in seconds.
        clip_duration (int): The duration of the clip in seconds.
        output_file (str): The output file path for the extracted clip.
    """
    if not video_duration:
        raise Exception("Could not get video duration")
    if not video_duration*0.7 > 120:
        raise Exception("Video too short")
    start_time = video_duration*0.15 + random.random()* (0.7*video_duration-clip_duration)
    
    temp_output_file = output_file + ".tmp.mp4"
    if os.path.exists(temp_output_file):
        os.remove(temp_output_file)

    use_nvenc = nvenc_runtime_available()
    input_options = []
    if use_nvenc and get_bool_setting("USE_CUDA_DECODE", False):
        input_options = ["-hwaccel", "cuda"]

    def build_command(use_gpu_encode):
        decode_options = input_options if use_gpu_encode else []
        return [
            _get_ffmpeg_binary(),
            '-y',
            '-hide_banner',
            '-loglevel', 'error',
            '-ss', str(start_time),
            *decode_options,
            '-i', video_url,
            '-t', str(clip_duration + 0.5),
            '-map', '0:v:0',
            '-an',
            '-sn',
            '-dn',
            *get_background_clip_encode_args(use_gpu_encode),
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            temp_output_file
        ]
    
    try:
        subprocess.run(build_command(use_nvenc), check=True)
    except subprocess.CalledProcessError as error:
        if not use_nvenc:
            raise
        if os.path.exists(temp_output_file):
            os.remove(temp_output_file)
        print(f"NVENC background clip extraction failed, retrying with CPU x264. Error: {error}")
        subprocess.run(build_command(False), check=True)

    _validate_video_clip(temp_output_file, expected_duration=clip_duration)
    if os.path.exists(output_file):
        os.remove(output_file)
    os.replace(temp_output_file, output_file)
    return output_file


def get_aspect_ratio(video_file):
    cmd = 'ffprobe -i "{}" -v quiet -print_format json -show_format -show_streams'.format(video_file)
#     jsonstr = subprocess.getoutput(cmd)
    jsonstr = subprocess.check_output(cmd, shell=True, encoding='utf-8')
    r = json.loads(jsonstr)
    # look for "codec_type": "video". take the 1st one if there are mulitple
    video_stream_info = [x for x in r['streams'] if x['codec_type']=='video'][0]
    if 'display_aspect_ratio' in video_stream_info and video_stream_info['display_aspect_ratio']!="0:1":
        a,b = video_stream_info['display_aspect_ratio'].split(':')
        dar = int(a)/int(b)
    else:
        # some video do not have the info of 'display_aspect_ratio'
        w,h = video_stream_info['width'], video_stream_info['height']
        dar = int(w)/int(h)
        ## not sure if we should use this
        #cw,ch = video_stream_info['coded_width'], video_stream_info['coded_height']
        #sar = int(cw)/int(ch)
    if 'sample_aspect_ratio' in video_stream_info and video_stream_info['sample_aspect_ratio']!="0:1":
        # some video do not have the info of 'sample_aspect_ratio'
        a,b = video_stream_info['sample_aspect_ratio'].split(':')
        sar = int(a)/int(b)
    else:
        sar = dar
    par = dar/sar
    return dar
