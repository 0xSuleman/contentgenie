from contentgenie.audio.voice_module import VoiceModule
from contentgenie.gpt import story_package_gpt
from contentgenie.config.languages import Language
from contentgenie.engine.content_short_engine import ContentShortEngine


class FactsShortEngine(ContentShortEngine):

    def __init__(self, voiceModule: VoiceModule, facts_type: str, background_video_name: str, background_music_name: str,short_id="",
                 num_images=None, watermark=None, language:Language = Language.ENGLISH,
                 creative_brief="", audience="General audience", tone="Cinematic and curious",
                 creator_angle="Explain why this matters to viewers today", target_duration=50,
                 quality_mode="Production", rights_confirmed=False,
                 footage_mode="Manual library selection", footage_style="Mixed",
                 footage_intensity="High", allow_youtube_cc=True, avoid_recent_footage=True,
                 music_mode="Manual library selection"):
        super().__init__(short_id=short_id, short_type="facts_shorts", background_video_name=background_video_name, background_music_name=background_music_name,
                 num_images=num_images, watermark=watermark, language=language, voiceModule=voiceModule,
                 creative_brief=creative_brief, audience=audience, tone=tone,
                 creator_angle=creator_angle, target_duration=target_duration,
                 quality_mode=quality_mode, rights_confirmed=rights_confirmed,
                 footage_mode=footage_mode, footage_style=footage_style,
                 footage_intensity=footage_intensity, allow_youtube_cc=allow_youtube_cc,
                 avoid_recent_footage=avoid_recent_footage, music_mode=music_mode)
        if not short_id:
            self._db_facts_type = facts_type

    def _generateScript(self):
        """
        Implements Abstract parent method to generate the script for the Facts short.
        """
        package = story_package_gpt.generate_facts_story_package(
            self._db_facts_type,
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
        self._db_quality_report = package.get("quality_report", {})
        self._db_research_sources = package.get("research_sources", [])
        self._db_originality_angle = package.get("originality_angle", "")

