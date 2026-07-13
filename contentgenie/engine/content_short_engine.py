import datetime
import json
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from abc import abstractmethod

from contentgenie.audio import audio_utils
from contentgenie.audio import sfx_library
from contentgenie.audio.audio_duration import get_asset_duration
from contentgenie.audio.voice_module import VoiceModule
from contentgenie.config.asset_db import AssetDatabase
from contentgenie.config.languages import Language
from contentgenie.config.render_settings import (
    get_background_music_volume,
    get_caption_max_chars,
    get_caption_settings,
    get_caption_style,
    get_pop_caption_colors,
    get_pop_caption_settings,
    get_image_overlay_settings,
    subscribe_animation_enabled,
    uppercase_captions,
)
from contentgenie.editing_framework.editing_engine import (EditingEngine,
                                                       EditingStep)
from contentgenie.editing_utils import captions, editing_images
from contentgenie.editing_utils.handle_videos import extract_random_clip_from_video
from contentgenie.engine.abstract_content_engine import AbstractContentEngine
from contentgenie.gpt import gpt_editing, gpt_translate, gpt_yt
from contentgenie.quality.video_quality import validate_rendered_short
from contentgenie.footage.service import FootageService
from contentgenie.music.service import MusicService


class ContentShortEngine(AbstractContentEngine):

    def __init__(self, short_type: str, background_video_name: str, background_music_name: str, voiceModule: VoiceModule, short_id="",
                 num_images=None, watermark=None, language: Language = Language.ENGLISH,
                 creative_brief="", audience="General audience", tone="Cinematic and curious",
                 creator_angle="Explain why this matters to viewers today", target_duration=50,
                 quality_mode="Production", rights_confirmed=False,
                 footage_mode="Manual library selection", footage_style="Mixed",
                 footage_intensity="High", allow_youtube_cc=True, avoid_recent_footage=True,
                 music_mode="Manual library selection"):
        if not short_id and not rights_confirmed:
            raise ValueError("Commercial media rights must be confirmed before creating a publishable short.")
        super().__init__(short_id, short_type, language, voiceModule)
        if not short_id:
            if (num_images):
                self._db_num_images = num_images
            if (watermark):
                self._db_watermark = watermark
            self._db_background_video_name = background_video_name
            self._db_background_music_name = background_music_name
            self._db_creative_brief = creative_brief or ""
            self._db_audience = audience or "General audience"
            self._db_tone = tone or "Cinematic and curious"
            self._db_creator_angle = creator_angle or "Explain why this matters to viewers today"
            self._db_target_duration = max(30, min(int(target_duration or 50), 58))
            self._db_quality_mode = quality_mode or "Production"
            self._db_rights_confirmed = bool(rights_confirmed)
            self._db_footage_mode = footage_mode or "Manual library selection"
            self._db_footage_style = footage_style or "Mixed"
            self._db_footage_intensity = footage_intensity or "High"
            self._db_allow_youtube_cc = bool(allow_youtube_cc)
            self._db_avoid_recent_footage = bool(avoid_recent_footage)
            self._db_music_mode = music_mode or "Manual library selection"

        self._music_selection_lock = threading.Lock()

        self.stepDict = {
            1:  self._generateScript,
            2:  self._generateTempAudio,
            3:  self._speedUpAudio,
            4:  self._timeCaptions,
            5:  self._generateImageSearchTerms,
            6:  self._generateImageUrls,
            7:  self._chooseBackgroundMusic,
            8:  self._chooseBackgroundVideo,
            9:  self._prepareBackgroundAssets,
            10: self._prepareCustomAssets,
            11: self._editAndRenderShort,
            12: self._validateRenderedShort,
            13: self._addYoutubeMetadata,
        }

    @abstractmethod
    def _generateScript(self):
        self._db_script = ""

    def _generateTempAudio(self):
        self._startImagePrefetch()
        if not self._db_script:
            raise NotImplementedError("generateScript method must set self._db_script.")
        if (self._db_temp_audio_path):
            return
        self.verifyParameters(text=self._db_script)
        script = self._db_script
        if (self._db_language != Language.ENGLISH.value):
            self._db_translated_script = gpt_translate.translateContent(script, self._db_language)
            script = self._db_translated_script
        self._db_temp_audio_path = self.voiceModule.generate_voice(
            script, self.dynamicAssetDir + "temp_audio_path.wav")

    def _speedUpAudio(self):
        if (self._db_audio_path):
            return
        self.verifyParameters(tempAudioPath=self._db_temp_audio_path)
        self._db_audio_path = audio_utils.speedUpAudio(
            self._db_temp_audio_path,
            self.dynamicAssetDir+"audio_voice.wav",
            max_duration=min(float(self._db_target_duration or 50) + 2, 58),
        )

    def _timeCaptions(self):
        self.verifyParameters(audioPath=self._db_audio_path)
        whisper_analysis = audio_utils.audioToText(self._db_audio_path)
        self._db_timed_words = captions.getWordsWithTime(whisper_analysis)
        self._db_timed_captions = captions.getCaptionsWithTime(
            whisper_analysis,
            maxCaptionSize=get_caption_max_chars(),
        )

    def _generateImageSearchTerms(self):
        self.verifyParameters(captionsTimed=self._db_timed_captions)
        if self._db_num_images:
            if self._db_image_prompts:
                self._db_timed_image_searches = gpt_editing.assignImagePromptsToCaptions(
                    self._db_timed_captions,
                    self._db_image_prompts,
                    timed_words=self._db_timed_words,
                    n=self._db_num_images,
                )
            else:
                self._db_timed_image_searches = gpt_editing.getImageQueryPairs(
                    self._db_timed_captions, n=self._db_num_images)
        self._startBackgroundPrefetch()

    def _generateImageUrls(self):
        if self._db_timed_image_searches:
            generated_paths = self._awaitImagePrefetch()
            if len(generated_paths) >= len(self._db_timed_image_searches):
                self._db_timed_image_urls = [
                    (timing, generated_paths[index])
                    for index, (timing, _prompt) in enumerate(self._db_timed_image_searches)
                ]
            else:
                self._db_timed_image_urls = editing_images.getImageUrlsTimed(
                    self._db_timed_image_searches, asset_dir=self.dynamicAssetDir)

    def _startImagePrefetch(self):
        if not self._db_num_images or not self._db_image_prompts or self._db_generated_image_paths:
            return
        if getattr(self, "_image_prefetch_future", None):
            return
        self._image_prefetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="contentgenie-images")
        self._image_prefetch_future = self._image_prefetch_executor.submit(
            editing_images.generateImageFiles,
            list(self._db_image_prompts)[:int(self._db_num_images)],
            None,
            self.dynamicAssetDir,
        )

    def _awaitImagePrefetch(self):
        existing = list(self._db_generated_image_paths or [])
        future = getattr(self, "_image_prefetch_future", None)
        if not future:
            if existing:
                return existing
            self._startImagePrefetch()
            future = getattr(self, "_image_prefetch_future", None)
        if not future:
            return []
        try:
            paths = list(future.result())
            self._db_generated_image_paths = paths
            return paths
        finally:
            executor = getattr(self, "_image_prefetch_executor", None)
            if executor:
                executor.shutdown(wait=True)
            self._image_prefetch_future = None
            self._image_prefetch_executor = None

    def _chooseBackgroundMusic(self):
        with self._music_selection_lock:
            if self._db_background_music_url:
                return
            automatic = self._db_music_mode == "Automatic script match"
            if automatic:
                selected = MusicService().select_for_script(
                    script=self._db_script,
                    direction=self._db_music_direction or {},
                    target_duration=float(self._db_target_duration or 50),
                    logger=self.logger,
                )
                self._db_background_music_name = selected["name"]
                self._db_background_music_url = selected["path"]
                metadata = selected.get("metadata") or {}
                self._db_music_attribution = {
                    "title": metadata.get("title") or selected["name"],
                    "creator": metadata.get("creator") or "Unknown creator",
                    "source": metadata.get("source") or "Openverse",
                    "source_key": metadata.get("source_key") or "",
                    "source_url": metadata.get("source_url") or "",
                    "license_name": metadata.get("license_name") or "",
                    "license_url": metadata.get("license_url") or "",
                    "attribution": metadata.get("attribution") or "",
                    "match_score": metadata.get("match_score"),
                    "evidence_path": metadata.get("evidence_path") or "",
                }
                return

            self._db_background_music_url = AssetDatabase.get_asset_link(self._db_background_music_name)
            record = AssetDatabase.get_asset_record(self._db_background_music_name) or {}
            metadata = record.get("metadata") or {}
            if metadata.get("licensed_music"):
                self._db_music_attribution = {
                    key: metadata.get(key)
                    for key in (
                        "title", "creator", "source", "source_key", "source_url",
                        "license_name", "license_url", "attribution", "match_score", "evidence_path",
                    )
                }

    def _chooseBackgroundVideo(self):
        if self._db_footage_mode == "Automatic licensed gameplay":
            if self._db_background_trimmed:
                return
            self._db_background_video_name = "Automatic licensed gameplay"
            self._db_background_video_url = "pending automatic licensed footage"
            self._db_background_video_duration = 1
            return
        self._db_background_video_url = AssetDatabase.get_asset_link(
            self._db_background_video_name)
        self._db_background_video_duration = AssetDatabase.get_asset_duration(
            self._db_background_video_name)

    def _startBackgroundPrefetch(self):
        if self._db_background_trimmed or getattr(self, "_background_prefetch_future", None):
            return
        self._background_prefetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="contentgenie-footage")
        self._background_prefetch_future = self._background_prefetch_executor.submit(self._prepareBackgroundAssetsNow)

    def _prepareBackgroundAssets(self):
        future = getattr(self, "_background_prefetch_future", None)
        if not future:
            return self._prepareBackgroundAssetsNow()
        try:
            return future.result()
        finally:
            executor = getattr(self, "_background_prefetch_executor", None)
            if executor:
                executor.shutdown(wait=True)
            self._background_prefetch_future = None
            self._background_prefetch_executor = None

    def _prepareBackgroundAssetsNow(self):
        if not self._db_background_music_url:
            self._chooseBackgroundMusic()
        if not self._db_background_video_url:
            self._chooseBackgroundVideo()
        if not self._db_voiceover_duration:
            self.logger("Rendering short: (1/4) preparing voice asset...")
            self._db_audio_path, self._db_voiceover_duration = get_asset_duration(
                self._db_audio_path, isVideo=False)

        if self._db_footage_mode == "Automatic licensed gameplay":
            if not self._db_background_trimmed:
                self.logger("Rendering short: (2/4) discovering and scoring licensed gameplay...")
                service = FootageService()
                preferred_cut_times = [
                    float(timing[1])
                    for timing, _text in (self._db_timed_captions or [])
                    if timing and len(timing) >= 2
                ]
                preferred_cut_times.extend(
                    float(item.get("set_time_start", 0))
                    for item in sfx_library.resolve_sfx_cues(
                        self._db_sfx_cues,
                        self._db_timed_words,
                        self._db_voiceover_duration,
                    )
                    if item.get("set_time_start") is not None
                )
                background_path, segments = service.create_background(
                    target_duration=float(self._db_voiceover_duration),
                    output_path=self.dynamicAssetDir + "licensed_gameplay_background.mp4",
                    style=self._db_footage_style or "Mixed",
                    intensity=self._db_footage_intensity or "High",
                    allow_youtube=bool(self._db_allow_youtube_cc),
                    avoid_recent=bool(self._db_avoid_recent_footage),
                    content_id=self.id,
                    logger=self.logger,
                    preferred_cut_times=preferred_cut_times,
                )
                self._db_background_trimmed = background_path
                self._db_background_video_url = background_path
                self._db_background_video_duration = float(self._db_voiceover_duration)
                self._db_footage_segments = segments
                self._db_footage_attributions = service.attribution_lines(segments)
            return

        self.verifyParameters(
            voiceover_audio_url=self._db_audio_path,
            video_duration=self._db_background_video_duration,
            background_video_url=self._db_background_video_url, music_url=self._db_background_music_url)
        if not self._db_background_trimmed:
            self.logger("Rendering short: (2/4) preparing background video asset...")
            self._db_background_trimmed = extract_random_clip_from_video(
                self._db_background_video_url, self._db_background_video_duration, self._db_voiceover_duration, self.dynamicAssetDir + "clipped_background.mp4")

    def _prepareCustomAssets(self):
        self.logger("Rendering short: (3/4) preparing custom assets...")
        pass

    def _editAndRenderShort(self):
        self.verifyParameters(
            voiceover_audio_url=self._db_audio_path,
            video_duration=self._db_background_video_duration,
            music_url=self._db_background_music_url)

        outputPath = self.dynamicAssetDir+"rendered_video.mp4"
        if not (os.path.exists(outputPath)):
            self.logger("Rendering short: Starting automated editing...")
            videoEditor = EditingEngine()
            videoEditor.addEditingStep(EditingStep.ADD_VOICEOVER_AUDIO, {
                                       'url': self._db_audio_path})
            videoEditor.addEditingStep(EditingStep.ADD_BACKGROUND_MUSIC, {'url': self._db_background_music_url,
                                                                          'loop_background_music': self._db_voiceover_duration,
                                                                          "volume_percentage": get_background_music_volume()})
            self._addSfxEditingSteps(videoEditor)
            self._addBackgroundVideoEditingStep(videoEditor)
            self._addSubscribeAnimation(videoEditor)

            if self._db_watermark:
                videoEditor.addEditingStep(EditingStep.ADD_WATERMARK, {
                                           'text': self._db_watermark})

            caption_type = EditingStep.ADD_CAPTION_SHORT_ARABIC if self._db_language == Language.ARABIC.value else EditingStep.ADD_CAPTION_SHORT
            self._addCaptionEditingSteps(videoEditor, caption_type)
            if self._db_num_images:
                image_settings = get_image_overlay_settings()
                for timing, image_url in self._db_timed_image_urls:
                    videoEditor.addEditingStep(EditingStep.SHOW_IMAGE, {
                        'url': image_url,
                        'set_time_start': timing[0],
                        'set_time_end': timing[1],
                        **image_settings,
                    })
            print("***** SCHEMA FOR RENDERING ****")
            print(videoEditor.dumpEditingSchema())
            print("***** SCHEMA FOR RENDERING ****")
            videoEditor.renderVideo(outputPath, logger= self.logger if self.logger is not self.default_logger else None)

        self._db_video_path = outputPath

    def _addBackgroundVideoEditingStep(self, videoEditor):
        if self._db_footage_mode == "Automatic licensed gameplay":
            videoEditor.addEditingStep(EditingStep.ADD_BACKGROUND_VIDEO, {
                'url': self._db_background_trimmed,
                'set_time_start': 0,
                'set_time_end': float(self._db_voiceover_duration),
            })
            return
        videoEditor.addEditingStep(EditingStep.CROP_1920x1080, {
            'url': self._db_background_trimmed,
        })

    def _addSfxEditingSteps(self, videoEditor):
        for sfx in sfx_library.resolve_sfx_cues(
            self._db_sfx_cues,
            self._db_timed_words,
            self._db_voiceover_duration,
        ):
            videoEditor.addEditingStep(EditingStep.INSERT_AUDIO, sfx)

    def _addSubscribeAnimation(self, videoEditor):
        if not subscribe_animation_enabled():
            return
        asset_name = "subscribe-animation" if AssetDatabase.asset_exists("subscribe-animation") else "subscribe animation"
        start = max(float(self._db_voiceover_duration or 0) - 5.0, 5.0)
        videoEditor.addEditingStep(EditingStep.ADD_SUBSCRIBE_ANIMATION, {
            "url": AssetDatabase.get_asset_link(asset_name),
            "set_time_start": start,
            "set_time_end": float(self._db_voiceover_duration),
        })

    def _addCaptionEditingSteps(self, videoEditor, caption_type):
        if get_caption_style() == "Color bounce":
            self._addPopCaptionEditingSteps(videoEditor)
            return

        caption_settings = get_caption_settings()
        for timing, text in self._db_timed_captions:
            caption_text = text.upper() if uppercase_captions() else text
            videoEditor.addEditingStep(caption_type, {
                'text': caption_text,
                'set_time_start': timing[0],
                'set_time_end': timing[1],
                **caption_settings,
            })

    def _addPopCaptionEditingSteps(self, videoEditor):
        caption_settings = get_pop_caption_settings()
        colors = get_pop_caption_colors()
        color_index = 0
        timed_words = self._db_timed_words or []
        if not timed_words:
            for timing, text in self._db_timed_captions:
                words = [word for word in text.split() if word.strip()]
                if not words:
                    continue
                start, end = timing
                word_duration = max((end - start) / len(words), 0.08)
                timed_words.extend([((start + index * word_duration, min(start + (index + 1) * word_duration, end)), word) for index, word in enumerate(words)])

        for timing, word in timed_words:
            word_start, word_end = timing
            word_end = max(word_end, word_start + 0.08)
            caption_text = word.upper() if uppercase_captions() else word
            videoEditor.addEditingStep(EditingStep.ADD_CAPTION_POP, {
                'text': caption_text,
                'set_time_start': word_start,
                'set_time_end': word_end,
                **caption_settings,
                'color': colors[color_index % len(colors)],
            })
            color_index += 1

    def _addYoutubeMetadata(self):
        if not os.path.exists('videos/'):
            os.makedirs('videos')
        if not self._db_yt_title or not self._db_yt_description:
            self._db_yt_title, self._db_yt_description = gpt_yt.generate_title_description_dict(self._db_script)
        footage_attributions = self._db_footage_attributions or []
        if footage_attributions and "Licensed gameplay credits:" not in self._db_yt_description:
            self._db_yt_description = (
                self._db_yt_description.rstrip()
                + "\n\nLicensed gameplay credits:\n"
                + "\n".join(f"- {line}" for line in footage_attributions)
            )
        music_attribution = self._db_music_attribution or {}
        music_credit = str(music_attribution.get("attribution") or "").strip()
        if music_credit and "Music credit:" not in self._db_yt_description:
            self._db_yt_description = (
                self._db_yt_description.rstrip()
                + f"\n\nMusic credit:\n- {music_credit}"
            )

        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        safe_title = re.sub(r"[^a-zA-Z0-9 '._-]", '', self._db_yt_title).strip(" .")[:90]
        newFileName = f"videos/{date_str}_{self.id[:8]} - {safe_title or 'YouTube Short'}"

        shutil.move(self._db_video_path, newFileName+".mp4")
        with open(newFileName+".txt", "w", encoding="utf-8") as f:
            f.write(
                f"---Youtube title---\n{self._db_yt_title}\n---Youtube description---\n{self._db_yt_description}")
        manifest = {
            "schema_version": 1,
            "content_id": self.id,
            "content_type": self.dataManager.contentType,
            "generated_at": now.isoformat(),
            "video_file": os.path.basename(newFileName + ".mp4"),
            "youtube": {
                "title": self._db_yt_title,
                "description": self._db_yt_description,
                "made_for_kids": False,
                "contains_ai_generated_visuals": bool(self._db_num_images),
                "altered_content_disclosure_review_required": bool(self._db_num_images),
            },
            "creative_direction": {
                "brief": self._db_creative_brief,
                "audience": self._db_audience,
                "tone": self._db_tone,
                "editorial_angle": self._db_creator_angle,
                "target_duration_seconds": self._db_target_duration,
                "quality_mode": self._db_quality_mode,
            },
            "script": self._db_script,
            "quality_report": self._db_quality_report or {},
            "video_quality_report": self._db_video_quality_report or {},
            "research_sources": self._db_research_sources or [],
            "originality_angle": self._db_originality_angle or "",
            "image_prompts": self._db_image_prompts or [],
            "sfx_cues": self._db_sfx_cues or [],
            "assets": {
                "background_video": self._db_background_video_name,
                "background_music": self._db_background_music_name,
                "music_mode": self._db_music_mode or "Manual library selection",
                "music_direction": self._db_music_direction or {},
                "licensed_music": music_attribution,
                "commercial_rights_confirmed_by_user": bool(self._db_rights_confirmed),
                "footage_mode": self._db_footage_mode or "Manual library selection",
                "footage_style": self._db_footage_style or "Mixed",
                "footage_intensity": self._db_footage_intensity or "High",
                "licensed_gameplay_attributions": footage_attributions,
                "licensed_gameplay_segments": self._db_footage_segments or [],
            },
            "human_review_checklist": [
                "Watch the entire exported video before uploading.",
                "Confirm every factual claim against the listed sources.",
                "Confirm commercial rights for music, footage, fonts, images, and sound effects.",
                "Choose the altered/synthetic content disclosure accurately in YouTube Studio.",
                "Confirm the title and description accurately represent this specific video.",
            ],
            "production_timings": self._db_stage_timings or {},
        }
        with open(newFileName+".json", "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
        self._db_video_path = newFileName+".mp4"
        self._db_ready_to_upload = True

    def _validateRenderedShort(self):
        self.verifyParameters(video_path=self._db_video_path)
        self.logger("Validating rendered short for publish readiness...")
        self._db_video_quality_report = validate_rendered_short(
            self._db_video_path,
            maximum_duration=60.0,
        )

    def get_quality_report(self):
        return self._db_quality_report or {}

    def get_output_summary(self):
        return {
            "title": self._db_yt_title or "YouTube Short",
            "description": self._db_yt_description or "",
            "quality_report": self._db_quality_report or {},
            "video_quality_report": self._db_video_quality_report or {},
            "research_sources": self._db_research_sources or [],
            "footage_attributions": self._db_footage_attributions or [],
            "music_attribution": self._db_music_attribution or {},
            "production_timings": self._db_stage_timings or {},
        }
