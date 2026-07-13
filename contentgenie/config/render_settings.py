from contentgenie.config.api_db import ApiKeyManager


def get_setting(name, default):
    value = ApiKeyManager.get_api_key(name)
    return value if value not in (None, "") else default


def get_int_setting(name, default, minimum=None, maximum=None):
    try:
        value = int(float(get_setting(name, default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_float_setting(name, default, minimum=None, maximum=None):
    try:
        value = float(get_setting(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_bool_setting(name, default=False):
    value = get_setting(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_image_generation_size():
    return (
        get_int_setting("AI_IMAGE_WIDTH", 720, 512, 1536),
        get_int_setting("AI_IMAGE_HEIGHT", 720, 512, 1536),
    )


def get_image_overlay_settings():
    max_width = get_int_setting("SHORT_IMAGE_MAX_WIDTH", 690, 128, 1080)
    max_height = get_int_setting("SHORT_IMAGE_MAX_HEIGHT", 690, 128, 1920)
    position = get_setting("SHORT_IMAGE_POSITION", "Top")
    y_by_position = {
        "Top": 50,
        "Upper middle": 220,
        "Center": "center",
        "Lower middle": 780,
        "Bottom": 1070,
    }
    y = y_by_position.get(position, 50)
    settings = {
        "auto_resize_image": {"maxWidth": max_width, "maxHeight": max_height},
        "normalize_image": {"maxWidth": max_width, "maxHeight": max_height},
        "screen_position": {"pos": ["center", y]},
    }
    if get_bool_setting("SHORT_IMAGE_MOTION", True):
        settings["ken_burns"] = {
            "start": 1.0,
            "end": get_float_setting("SHORT_IMAGE_MOTION_SCALE", 1.06, 1.0, 1.25),
        }
    return settings


def get_caption_settings():
    position = get_setting("SHORT_CAPTION_POSITION", "Center")
    y_by_position = {
        "Upper middle": 430,
        "Center": "center",
        "Lower third": 1120,
        "Bottom": 1370,
    }
    pos = y_by_position.get(position, "center")
    if pos != "center":
        pos = ["center", pos]
    return {
        "font_size": get_int_setting("SHORT_CAPTION_FONT_SIZE", 100, 32, 180),
        "color": get_setting("SHORT_CAPTION_COLOR", "white"),
        "stroke_width": get_int_setting("SHORT_CAPTION_STROKE_WIDTH", 3, 0, 12),
        "stroke_color": get_setting("SHORT_CAPTION_STROKE_COLOR", "black"),
        "size": [
            get_int_setting("SHORT_CAPTION_BOX_WIDTH", 900, 300, 1080),
            get_int_setting("SHORT_CAPTION_BOX_HEIGHT", 450, 80, 900),
        ],
        "screen_position": {"pos": pos},
    }


def get_caption_style():
    return get_setting("SHORT_CAPTION_STYLE", "Traditional")


def get_pop_caption_colors():
    raw_colors = get_setting("SHORT_POP_CAPTION_COLORS", "#FFD400,#00E5FF,#FF4FD8,#7CFF6B,#FFFFFF")
    colors = [color.strip() for color in raw_colors.split(",") if color.strip()]
    return colors or ["#FFD400", "#00E5FF", "#FF4FD8", "#7CFF6B", "#FFFFFF"]


def get_pop_caption_settings():
    settings = get_caption_settings()
    settings["font_size"] = get_int_setting("SHORT_POP_CAPTION_FONT_SIZE", settings["font_size"], 32, 220)
    settings["size"] = [
        get_int_setting("SHORT_POP_CAPTION_BOX_WIDTH", settings["size"][0], 300, 1080),
        get_int_setting("SHORT_POP_CAPTION_BOX_HEIGHT", 260, 80, 900),
    ]
    settings["bounce_scale"] = {
        "start": get_float_setting("SHORT_POP_CAPTION_SCALE_START", 0.55, 0.1, 1.2),
        "peak": get_float_setting("SHORT_POP_CAPTION_SCALE_PEAK", 1.18, 1.0, 2.5),
        "settle": 1.0,
        "attack": get_float_setting("SHORT_POP_CAPTION_ATTACK", 0.08, 0.01, 0.5),
        "release": get_float_setting("SHORT_POP_CAPTION_RELEASE", 0.16, 0.01, 0.8),
    }
    return settings


def get_caption_max_chars():
    return get_int_setting("SHORT_CAPTION_MAX_CHARS", 15, 6, 42)


def get_image_display_duration():
    return get_float_setting("SHORT_IMAGE_DISPLAY_SECONDS", 2.2, 0.25, 8.0)


def get_background_music_volume():
    return get_float_setting("SHORT_BACKGROUND_MUSIC_VOLUME", 0.07, 0.0, 1.0)


def subscribe_animation_enabled():
    return get_bool_setting("SHORT_SUBSCRIBE_ANIMATION", False)


def sfx_enabled():
    return get_bool_setting("SHORT_SFX_ENABLED", True)


def get_sfx_volume():
    return get_float_setting("SHORT_SFX_VOLUME", 0.35, 0.0, 1.0)


def get_sfx_max_cues():
    return get_int_setting("SHORT_SFX_MAX_CUES", 7, 0, 20)


def get_sfx_max_duration():
    return get_float_setting("SHORT_SFX_MAX_DURATION", 1.25, 0.1, 4.0)


def get_sfx_min_gap():
    return get_float_setting("SHORT_SFX_MIN_GAP", 1.2, 0.0, 8.0)


def get_visual_style_prompt():
    return get_setting(
        "SHORT_VISUAL_STYLE_PROMPT",
        "cinematic vertical YouTube Shorts storytime frame, realistic, emotionally clear, dramatic lighting, coherent subject, no text, no watermark",
    )


def uppercase_captions():
    return get_bool_setting("SHORT_CAPTION_UPPERCASE", True)
