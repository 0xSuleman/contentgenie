from contentgenie.audio.voice_module import VoiceModule
from contentgenie.config.asset_db import AssetDatabase
from contentgenie.config.languages import Language
from contentgenie.config.render_settings import (
    get_background_music_volume,
    get_image_overlay_settings,
)
from contentgenie.engine.content_short_engine import ContentShortEngine
from contentgenie.editing_framework.editing_engine import EditingEngine, EditingStep, Flow
from contentgenie.gpt import story_package_gpt
import os


class RedditShortEngine(ContentShortEngine):
    # Mapping of variable names to database paths
    def __init__(self,voiceModule: VoiceModule, background_video_name: str, background_music_name: str,short_id="",
                 num_images=None, watermark=None, language:Language = Language.ENGLISH,
                 creative_brief="", audience="General audience", tone="Suspenseful storytime",
                 creator_angle="Tell an original, emotionally honest story with a useful takeaway",
                 target_duration=50, quality_mode="Production", rights_confirmed=False,
                 footage_mode="Manual library selection", footage_style="Mixed",
                 footage_intensity="High", allow_youtube_cc=True, avoid_recent_footage=True,
                 music_mode="Manual library selection"):
        super().__init__(short_id=short_id, short_type="reddit_shorts", background_video_name=background_video_name, background_music_name=background_music_name,
                 num_images=num_images, watermark=watermark, language=language, voiceModule=voiceModule,
                 creative_brief=creative_brief, audience=audience, tone=tone,
                 creator_angle=creator_angle, target_duration=target_duration,
                 quality_mode=quality_mode, rights_confirmed=rights_confirmed,
                 footage_mode=footage_mode, footage_style=footage_style,
                 footage_intensity=footage_intensity, allow_youtube_cc=allow_youtube_cc,
                 avoid_recent_footage=avoid_recent_footage, music_mode=music_mode)
    
    def _generateScript(self):
        """
        Implements Abstract parent method to generate the script for the reddit short
        """
        self.logger("Generating reddit story package")
        package = story_package_gpt.generate_reddit_story_package(
            num_images=self._db_num_images or 0,
            creative_brief=self._db_creative_brief,
            audience=self._db_audience,
            tone=self._db_tone,
            creator_angle=self._db_creator_angle,
            target_duration=self._db_target_duration,
            quality_mode=self._db_quality_mode,
        )
        self._db_script = package["script"]
        self._db_image_prompts = package.get("image_prompts", [])
        self._db_sfx_cues = package.get("sfx_cues", [])
        self._db_music_direction = package.get("music_direction", {})
        self._db_yt_title = package.get("youtube_title", "")
        self._db_yt_description = package.get("youtube_description", "")
        self._db_reddit_question = package.get("reddit_question") or package["script"][:120]
        self._db_reddit_post = package.get("reddit_post") or {}
        self._db_quality_report = package.get("quality_report", {})
        self._db_research_sources = package.get("research_sources", [])
        self._db_originality_angle = package.get("originality_angle", "")

    def _prepareCustomAssets(self):
        """
        Override parent method to generate custom reddit image asset
        """
        self.logger("Rendering short: (3/4) preparing custom reddit image...")
        self.verifyParameters(question=self._db_reddit_question,)
        reddit_post = self._db_reddit_post or {}
        title = reddit_post.get("title") or self._db_reddit_question
        header = reddit_post.get("header") or "u/storytime - 4 months ago"
        n_comments = reddit_post.get("comments") or "3.4k"
        n_upvotes = reddit_post.get("upvotes") or "8.1k"
        imageEditingEngine = EditingEngine()
        imageEditingEngine.ingestFlow(Flow.WHITE_REDDIT_IMAGE_FLOW, {
            "username_text": header,
            "ncomments_text": n_comments,
            "nupvote_text": n_upvotes,
            "question_text": title
        })
        imageEditingEngine.renderImage(
            self.dynamicAssetDir+"redditThreadImage.png")
        self._db_reddit_thread_image = self.dynamicAssetDir+"redditThreadImage.png"
    
    def _editAndRenderShort(self):
        """
        Override parent method to customize video rendering sequence by adding a Reddit image
        """
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
            videoEditor.addEditingStep(EditingStep.ADD_REDDIT_IMAGE, {
                                       'url': self._db_reddit_thread_image})
            
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

            videoEditor.renderVideo(outputPath, logger= self.logger if self.logger is not self.default_logger else None)

        self._db_video_path = outputPath

