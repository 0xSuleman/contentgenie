from urllib.error import HTTPError
import contextlib
import io
from contentgenie.config.path_utils import get_program_path
import os
from pathlib import Path
from contentgenie.config.path_utils import handle_path
import numpy as np
from typing import Any, Dict, List, Union
from moviepy import (AudioFileClip, CompositeVideoClip, CompositeAudioClip, ImageClip,
                    TextClip, VideoFileClip, AudioClip)
from moviepy.Clip import Clip
from moviepy import vfx, afx
from contentgenie.config.performance import get_moviepy_video_kwargs
from contentgenie.editing_framework.fast_caption_renderer import burn_pop_captions, split_pop_captions
from contentgenie.editing_framework.rendering_logger import MoviepyProgressLogger
import json

def load_schema(json_path):
    return json.loads(open(json_path, 'r', encoding='utf-8').read())

class CoreEditingEngine:

    def generate_image(self, schema:Dict[str, Any],output_file , logger=None):
        assets = dict(sorted(schema['visual_assets'].items(), key=lambda item: item[1]['z']))
        clips = []

        for asset_key in assets:
            asset = assets[asset_key]
            asset_type = asset['type']
            if asset_type == 'image':
                clip = self.process_image_asset(asset)
            elif asset_type == 'text':
                clip = self.process_text_asset(asset)
            else:
                raise ValueError(f'Invalid asset type: {asset_type}')
            clips.append(clip)

        image = CompositeVideoClip(clips)
        try:
            image.save_frame(output_file)
        finally:
            image.close()
            for clip in clips:
                clip.close()
        return output_file

    def generate_video(self, schema:Dict[str, Any], output_file, logger=None, force_duration=None, threads=None, _skip_fast_captions=False, _lossless=False) -> None:
        if not _skip_fast_captions:
            base_schema, pop_captions = split_pop_captions(schema)
            if pop_captions:
                output_path = Path(output_file)
                intermediate_path = output_path.with_suffix(".caption-base.mp4")
                final_path = output_path.with_suffix(".caption-final.mp4")
                intermediate_path.unlink(missing_ok=True)
                final_path.unlink(missing_ok=True)
                try:
                    self.generate_video(
                        base_schema,
                        str(intermediate_path),
                        logger=logger,
                        force_duration=force_duration,
                        threads=threads,
                        _skip_fast_captions=True,
                        _lossless=True,
                    )
                    if logger:
                        logger("Applying animated captions with the accelerated renderer...")
                    burn_pop_captions(intermediate_path, final_path, pop_captions)
                    os.replace(final_path, output_path)
                    return output_file
                except Exception as error:
                    print(f"Accelerated caption render failed, retrying with the compatibility renderer. Error: {error}")
                    output_path.unlink(missing_ok=True)
                finally:
                    intermediate_path.unlink(missing_ok=True)
                    final_path.unlink(missing_ok=True)

        visual_assets = dict(sorted(schema['visual_assets'].items(), key=lambda item: item[1]['z']))
        audio_assets = dict(sorted(schema['audio_assets'].items(), key=lambda item: item[1]['z']))
        
        visual_clips = []
        for asset_key in visual_assets:
            asset = visual_assets[asset_key]
            asset_type = asset['type']
            if asset_type == 'video':
                clip = self.process_video_asset(asset)
            elif asset_type == 'image':
                # clip = self.process_image_asset(asset)
                try:
                    clip = self.process_image_asset(asset)
                except Exception as e:
                    print(f"Failed to load image {asset['parameters']['url']}. Error : {str(e)}")
                    continue
            elif asset_type == 'text':
                clip = self.process_text_asset(asset)
            else:
                raise ValueError(f'Invalid asset type: {asset_type}')

            visual_clips.append(clip)
        
        audio_clips = []

        for asset_key in audio_assets:
            asset = audio_assets[asset_key]
            asset_type = asset['type']
            if asset_type == "audio":
                audio_clip = self.process_audio_asset(asset)
            else:
                raise ValueError(f"Invalid asset type: {asset_type}")

            audio_clips.append(audio_clip)
        video = CompositeVideoClip(visual_clips)
        if(audio_clips):
            audio = CompositeAudioClip(audio_clips)
            video = video.with_audio(audio)
            video = video.with_duration(audio.duration)
        if force_duration:
            video = video.with_duration(force_duration)

        my_logger = MoviepyProgressLogger(callBackFunction=logger) if logger else None
        write_kwargs = get_moviepy_video_kwargs(threads=threads, logger=my_logger, lossless=_lossless)
        try:
            try:
                video.write_videofile(output_file, **write_kwargs)
            except Exception as error:
                if write_kwargs.get("codec") != "h264_nvenc":
                    raise
                print(f"NVENC render failed, retrying with CPU x264. Error: {error}")
                fallback_kwargs = get_moviepy_video_kwargs(threads=threads, logger=my_logger, use_nvenc=False, lossless=_lossless)
                video.write_videofile(output_file, **fallback_kwargs)
        finally:
            video.close()
            for clip in [*visual_clips, *audio_clips]:
                clip.close()
        return output_file
    
    def generate_audio(self, schema:Dict[str, Any], output_file, logger=None) -> None:
        audio_assets = dict(sorted(schema['audio_assets'].items(), key=lambda item: item[1]['z']))
        audio_clips = []

        for asset_key in audio_assets:
            asset = audio_assets[asset_key]
            asset_type = asset['type']
            if asset_type == "audio":
                audio_clip = self.process_audio_asset(asset)
            else:
                raise ValueError(f"Invalid asset type: {asset_type}")

            audio_clips.append(audio_clip)
        audio = CompositeAudioClip(audio_clips)
        audio.fps = 44100
        try:
            if logger:
                my_logger = MoviepyProgressLogger(callBackFunction=logger)
                audio.write_audiofile(output_file, logger=my_logger)
            else:
                audio.write_audiofile(output_file)
        finally:
            audio.close()
            for clip in audio_clips:
                clip.close()
        return output_file
    # Process common actions
    def process_common_actions(self,
                                   clip: Union[VideoFileClip, ImageClip, TextClip, AudioFileClip],
                                   actions: List[Dict[str, Any]]) -> Union[VideoFileClip, AudioFileClip, ImageClip, TextClip]:
        for action in actions:
            if action['type'] == 'set_time_start':
                clip = clip.with_start(action['param'])
                continue
   
            if action['type'] == 'set_time_end':
                clip = clip.with_end(action['param'])
                continue
            
            if action['type'] == 'subclip':
                clip = clip.subclipped(**action['param'])
                continue

        return clip

    # Process common visual clip actions
    def process_common_visual_actions(self,
                                   clip: Clip,
                                   actions: List[Dict[str, Any]]) -> Union[VideoFileClip, ImageClip, TextClip]:
        clip = self.process_common_actions(clip, actions)
        for action in actions:
 
            if action['type'] == 'resize':
                clip = clip.with_effects([vfx.Resize(**action['param'])])
                continue

            if action['type'] == 'bounce_scale':
                params = action['param']
                start = float(params.get('start', 0.55))
                peak = float(params.get('peak', 1.18))
                settle = float(params.get('settle', 1.0))
                attack = max(float(params.get('attack', 0.08)), 0.001)
                release = max(float(params.get('release', 0.16)), 0.001)

                def scale_at_time(t):
                    if t <= attack:
                        return start + (peak - start) * (t / attack)
                    if t <= attack + release:
                        return peak - (peak - settle) * ((t - attack) / release)
                    return settle

                clip = clip.with_effects([vfx.Resize(scale_at_time)])
                continue

            if action['type'] == 'ken_burns':
                params = action.get('param') or {}
                start_scale = float(params.get('start', 1.0))
                end_scale = float(params.get('end', 1.06))
                duration = max(float(clip.duration or 0.001), 0.001)

                def image_scale_at_time(t):
                    progress = min(max(float(t) / duration, 0.0), 1.0)
                    eased = progress * progress * (3 - 2 * progress)
                    return start_scale + (end_scale - start_scale) * eased

                clip = clip.with_effects([vfx.Resize(image_scale_at_time)])
                continue

            if action['type'] == 'crop':
                clip = clip.with_effects([vfx.Crop(**action['param'])])
                continue

            if action['type'] == 'screen_position':
                clip = clip.with_position(**action['param'])
                continue

            if action['type'] == 'green_screen':
                params = action['param']
                color = params['color'] if  params['color'] else [52, 255, 20]
                thr = params["threshold"] if params["threshold"] else 100
                s = params['stiffness'] if params['stiffness'] else 5
                clip = clip.with_effects([vfx.MaskColor(color=color,threshold=thr, stiffness=s)])
                continue

            if action['type'] == 'normalize_image':
                clip = clip.image_transform(self.__normalize_frame)
                continue

            if action['type'] == 'auto_resize_image':
                ar = clip.aspect_ratio
                height = action['param']['maxHeight']
                width = action['param']['maxWidth']
                if ar <1:
                    clip = clip.with_effects([vfx.Resize((height*ar, height))])
                else:
                    clip = clip.with_effects([vfx.Resize((width, width/ar))])
                continue

        return clip

    # Process audio actions
    def process_audio_actions(self, clip: AudioClip,
                            actions: List[Dict[str, Any]]) -> AudioClip:
        clip = self.process_common_actions(clip, actions)
        for action in actions:
            if action['type'] in {'normalize_music', 'normalize_audio'}:
                clip = clip.with_effects([afx.AudioNormalize()])
                continue

            if action['type'] == 'loop_background_music':
                target_duration = action['param']
                # Skip a long library-track intro only when enough material remains.
                # This avoids looping a tail while still reaching the musical body quickly.
                available = max(float(clip.duration or 0) - float(target_duration), 0)
                start = min(max(float(clip.duration or 0) * 0.12, 3.0), available) if available >= 3 else 0
                if start:
                    clip = clip.subclipped(start)
                clip = clip.with_effects([afx.AudioLoop(duration=target_duration)])
                continue

            if action['type'] == 'audio_fade_in':
                clip = clip.with_effects([afx.AudioFadeIn(float(action['param']))])
                continue

            if action['type'] == 'audio_fade_out':
                clip = clip.with_effects([afx.AudioFadeOut(float(action['param']))])
                continue

            if action['type'] == 'volume_percentage':
                clip = clip.with_effects([afx.MultiplyVolume(action['param'])])
                continue

        return clip
    # Process individual asset types
    def process_video_asset(self, asset: Dict[str, Any]) -> VideoFileClip:
        params = {
            'filename': handle_path(asset['parameters']['url'])
        }
        if 'audio' in asset['parameters']:
            params['audio'] = asset['parameters']['audio']
        with contextlib.redirect_stdout(io.StringIO()):
            clip = VideoFileClip(**params)
        return self.process_common_visual_actions(clip, asset['actions'])

    def process_image_asset(self, asset: Dict[str, Any]) -> ImageClip:
        clip = ImageClip(asset['parameters']['url'])
        return self.process_common_visual_actions(clip, asset['actions'])

    def process_text_asset(self, asset: Dict[str, Any]) -> TextClip:
        text_clip_params = asset['parameters']
        
        if not (any(key in text_clip_params for key in ['text','fontsize', 'size'])):
            raise Exception('You must include at least a size or a fontsize to determine the size of your text')
        text_method = text_clip_params.get('method', 'label')
        clip_info = {
            'text': text_clip_params['text'],
            'font': text_clip_params.get('font'),
            'font_size': text_clip_params.get('font_size'),
            'color': text_clip_params.get('color'),
            'stroke_width': text_clip_params.get('stroke_width'),
            'stroke_color': text_clip_params.get('stroke_color'),
            'size': text_clip_params.get('size'),
            'method': text_method,
            'text_align': text_clip_params.get('text_align', 'center')
        }
        clip_info = {k: v for k, v in clip_info.items() if v is not None}
        clip = TextClip(**clip_info)
        return self.process_common_visual_actions(clip, asset['actions'])

    def process_audio_asset(self, asset: Dict[str, Any]) -> AudioFileClip:
        clip = AudioFileClip(asset['parameters']['url'])
        return self.process_audio_actions(clip, asset['actions'])
    
    def __normalize_image(self, clip):
        def f(get_frame, t):
            if f.normalized_frame is not None:
                return f.normalized_frame
            else:
                frame = get_frame(t)
                f.normalized_frame = self.__normalize_frame(frame)
                return f.normalized_frame

        f.normalized_frame = None

        return clip.fl(f)


    def __normalize_frame(self, frame):
        shape = np.shape(frame)
        [dimensions, ] = np.shape(shape)

        if dimensions == 2:
            (height, width) = shape
            normalized_frame = np.zeros((height, width, 3))
            for y in range(height):
                for x in range(width):
                    grey_value = frame[y][x]
                    normalized_frame[y][x] = (grey_value, grey_value, grey_value)
            return normalized_frame
        else:
            return frame
        

