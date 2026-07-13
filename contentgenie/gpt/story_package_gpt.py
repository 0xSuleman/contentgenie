import json
import os
import re
from datetime import datetime

import requests

from contentgenie.config.render_settings import get_sfx_max_cues, get_visual_style_prompt
from contentgenie.music.models import normalize_music_direction
from contentgenie.database.content_database import ContentDatabase
from contentgenie.gpt import gpt_utils


ALLOWED_SFX = {
    "riser", "whoosh", "impact", "hit", "reveal", "suspense",
    "door", "lock", "glass", "metal", "thunder", "footstep",
}
CLIFFHANGER_PHRASES = (
    "part two", "part 2", "to be continued", "you won't believe what happened next",
    "what happened next", "follow for the rest", "follow to find out",
)
GENERIC_HOOKS = (
    "did you know", "here are", "this is the story of", "you won't believe",
)
_GEMINI_GROUNDING_UNAVAILABLE_UNTIL = None


REDDIT_POST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "header": {"type": "string"},
        "comments": {"type": "string"},
        "upvotes": {"type": "string"},
    },
    "required": ["title", "header", "comments", "upvotes"],
}

STORY_PACKAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "youtube_title": {"type": "string"},
        "youtube_description": {"type": "string"},
        "reddit_question": {"type": "string"},
        "reddit_post": REDDIT_POST_SCHEMA,
        "image_prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "anchor_text": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["anchor_text", "prompt"],
            },
        },
        "sfx_cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "anchor_text": {"type": "string"},
                    "effect": {"type": "string", "enum": sorted(ALLOWED_SFX)},
                    "intensity": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["anchor_text", "effect", "intensity"],
            },
        },
        "music_direction": {
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "enum": ["curious", "suspenseful", "uplifting", "reflective", "playful", "urgent", "wonder", "neutral"],
                },
                "energy": {"type": "string", "enum": ["low", "medium", "high"]},
                "style": {
                    "type": "string",
                    "enum": ["cinematic ambient", "documentary", "electronic pulse", "acoustic", "orchestral", "lo-fi", "playful percussion", "minimal piano"],
                },
                "search_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["mood", "energy", "style", "search_terms"],
        },
        "originality_angle": {"type": "string"},
    },
    "required": [
        "script", "youtube_title", "youtube_description", "reddit_question",
        "reddit_post", "image_prompts", "sfx_cues", "music_direction", "originality_angle",
    ],
}

QUALITY_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "hook_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "retention_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "originality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "clarity_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "payoff_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "advertiser_safety_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "approved": {"type": "boolean"},
        "issues_fixed": {"type": "array", "items": {"type": "string"}},
        "review_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "overall_score", "hook_score", "retention_score", "originality_score",
        "clarity_score", "payoff_score", "advertiser_safety_score", "approved",
        "issues_fixed", "review_notes",
    ],
}

REVIEWED_PACKAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "package": STORY_PACKAGE_SCHEMA,
        "quality_review": QUALITY_REVIEW_SCHEMA,
    },
    "required": ["package", "quality_review"],
}


def _extract_json_object(text):
    text = str(text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            raise Exception("No JSON object found in Gemini story package response")
        return json.loads(text[start:end])


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _word_count(text):
    return len(re.findall(r"\b[\w'’-]+\b", str(text or ""), flags=re.UNICODE))


def _target_word_range(target_duration):
    target_duration = max(30, min(int(target_duration or 50), 58))
    target_words = round(target_duration * 2.7)
    return max(90, target_words - 14), min(170, target_words + 14)


def _truncate_at_word(text, max_chars):
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    shortened = text[:max_chars + 1].rsplit(" ", 1)[0].rstrip(" .,:;-!")
    return shortened or text[:max_chars]


def _exact_anchor(script, anchor):
    anchor = _clean_text(anchor).strip(".,!?;:\"'")
    if not anchor:
        return ""
    match = re.search(re.escape(anchor), script, flags=re.IGNORECASE)
    return script[match.start():match.end()] if match else ""


def _distributed_anchor(script, index, total, width=4):
    words = list(re.finditer(r"\b[\w'’-]+\b", script, flags=re.UNICODE))
    if not words:
        return ""
    width = min(width, len(words))
    last_start = max(0, len(words) - width)
    start = 0 if total <= 1 else round(last_start * index / max(total - 1, 1))
    return script[words[start].start():words[start + width - 1].end()]


def _normalize_sources(sources):
    normalized = []
    seen = set()
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        url = _clean_text(source.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append({
            "title": _clean_text(source.get("title")) or url,
            "url": url,
        })
    return normalized[:12]


def _normalize_package(payload, num_images, research_sources=None):
    if not isinstance(payload, dict):
        raise Exception("Gemini story package must be a JSON object")

    script = _clean_text(payload.get("script"))
    if not script:
        raise Exception("Gemini story package did not include a script")

    payload = dict(payload)
    payload["script"] = script
    payload["youtube_title"] = _truncate_at_word(payload.get("youtube_title") or script, 95)
    description = _clean_text(payload.get("youtube_description"))
    if "#shorts" not in description.lower():
        description = f"{description} #Shorts".strip()
    payload["youtube_description"] = description
    payload["reddit_question"] = _clean_text(payload.get("reddit_question"))
    reddit_post = payload.get("reddit_post") if isinstance(payload.get("reddit_post"), dict) else {}
    payload["reddit_post"] = {
        "title": _truncate_at_word(reddit_post.get("title") or payload["reddit_question"] or script, 150),
        "header": _truncate_at_word(reddit_post.get("header") or "u/storytime · original story", 60),
        "comments": _truncate_at_word(reddit_post.get("comments") or "3.4k", 12),
        "upvotes": _truncate_at_word(reddit_post.get("upvotes") or "8.1k", 12),
    }
    payload["originality_angle"] = _clean_text(payload.get("originality_angle"))

    prompts = payload.get("image_prompts") or []
    prompt_candidates = []
    for item in prompts:
        if isinstance(item, dict):
            prompt = item.get("prompt") or item.get("visual_prompt") or item.get("scene") or item.get("query")
            anchor = item.get("anchor_text") or item.get("anchor") or item.get("spoken_anchor")
        else:
            prompt, anchor = item, ""
        prompt = _clean_text(prompt)
        if prompt:
            prompt_candidates.append({"anchor_text": _clean_text(anchor), "prompt": prompt})

    normalized_prompts = []
    for index in range(int(num_images or 0)):
        item = prompt_candidates[index] if index < len(prompt_candidates) else {}
        anchor = _exact_anchor(script, item.get("anchor_text"))
        if not anchor:
            anchor = _distributed_anchor(script, index, int(num_images or 0))
        prompt = item.get("prompt") or f"Cinematic scene illustrating this moment: {anchor or script[:180]}"
        normalized_prompts.append({"anchor_text": anchor, "prompt": _clean_text(prompt)})
    payload["image_prompts"] = normalized_prompts

    sfx_cues = []
    seen_sfx = set()
    for item in payload.get("sfx_cues") or []:
        if not isinstance(item, dict):
            continue
        anchor = _exact_anchor(script, item.get("anchor_text") or item.get("anchor"))
        effect = _clean_text(item.get("effect") or item.get("sound") or item.get("type")).lower()
        intensity = _clean_text(item.get("intensity") or "medium").lower()
        key = (anchor.lower(), effect)
        if not anchor or effect not in ALLOWED_SFX or key in seen_sfx:
            continue
        seen_sfx.add(key)
        sfx_cues.append({
            "anchor_text": anchor,
            "effect": effect,
            "intensity": intensity if intensity in {"low", "medium", "high"} else "medium",
        })
    payload["sfx_cues"] = sfx_cues[:get_sfx_max_cues()]
    payload["music_direction"] = normalize_music_direction(payload.get("music_direction"))
    payload["research_sources"] = _normalize_sources(research_sources or payload.get("research_sources"))
    return payload


def _ngram_set(text, n=3):
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {tuple(words[index:index + n]) for index in range(max(0, len(words) - n + 1))}


def _similarity(first, second):
    left, right = _ngram_set(first), _ngram_set(second)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _recent_content(limit=12):
    try:
        docs = list(ContentDatabase().content_collection.find({}))
    except Exception:
        return []
    recent = []
    for doc in reversed(docs):
        script = _clean_text(doc.get("script"))
        if not script:
            continue
        recent.append({
            "title": _clean_text(doc.get("yt_title")),
            "hook": " ".join(script.split()[:22]),
            "script": script,
        })
        if len(recent) >= limit:
            break
    return recent


def audit_story_package(payload, target_duration=50, recent_content=None):
    script = _clean_text(payload.get("script"))
    words = _word_count(script)
    min_words, max_words = _target_word_range(target_duration)
    issues = []
    warnings = []
    score = 100

    if words < min_words:
        issues.append(f"Script is short for the target duration ({words} words; target {min_words}-{max_words}).")
        score -= min(25, min_words - words)
    elif words > max_words:
        issues.append(f"Script is long for the target duration ({words} words; target {min_words}-{max_words}).")
        score -= min(25, words - max_words)

    lowered = script.lower()
    if any(phrase in lowered for phrase in CLIFFHANGER_PHRASES):
        issues.append("The script contains sequel bait or an unresolved cliffhanger.")
        score -= 25
    hook = " ".join(script.split()[:16]).lower()
    if any(hook.startswith(phrase) for phrase in GENERIC_HOOKS):
        warnings.append("The hook starts with a common template phrase.")
        score -= 8
    if len(re.findall(r"[.!?]", script)) < 4:
        warnings.append("The script has limited sentence rhythm.")
        score -= 5
    if not payload.get("youtube_title"):
        issues.append("YouTube title is missing.")
        score -= 15
    if len(str(payload.get("youtube_title") or "")) > 100:
        issues.append("YouTube title exceeds 100 characters.")
        score -= 10

    invalid_anchors = 0
    for item in list(payload.get("image_prompts") or []) + list(payload.get("sfx_cues") or []):
        if not _exact_anchor(script, item.get("anchor_text") if isinstance(item, dict) else ""):
            invalid_anchors += 1
    if invalid_anchors:
        issues.append(f"{invalid_anchors} timed asset anchors do not exactly match the narration.")
        score -= min(15, invalid_anchors * 3)

    best_similarity = 0.0
    similar_title = ""
    for previous in recent_content or []:
        similarity = _similarity(script, previous.get("script"))
        if similarity > best_similarity:
            best_similarity = similarity
            similar_title = previous.get("title") or previous.get("hook") or "recent short"
    if best_similarity >= 0.55:
        issues.append(f"Script is too similar to '{similar_title}' ({best_similarity:.0%} phrase overlap).")
        score -= 30
    elif best_similarity >= 0.35:
        warnings.append(f"Script has noticeable overlap with a recent short ({best_similarity:.0%}).")
        score -= 10

    score = max(0, min(100, score))
    estimated_seconds = round(words / 2.7, 1) if words else 0
    critical = words < 75 or words > 185 or bool(invalid_anchors) or best_similarity >= 0.55
    return {
        "score": score,
        "approved": score >= 75 and not critical and not any("cliffhanger" in issue for issue in issues),
        "blocking": critical or any("cliffhanger" in issue for issue in issues),
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "word_count": words,
            "target_word_range": [min_words, max_words],
            "estimated_spoken_seconds": estimated_seconds,
            "recent_content_similarity": round(best_similarity, 4),
            "image_count": len(payload.get("image_prompts") or []),
            "sfx_count": len(payload.get("sfx_cues") or []),
        },
    }


def _today_history_context():
    today = datetime.now()
    return {
        "date_iso": today.strftime("%Y-%m-%d"),
        "month_day": f"{today.strftime('%B')} {today.day}",
    }


def _research_facts(subject, creative_brief):
    global _GEMINI_GROUNDING_UNAVAILABLE_UNTIL
    now = datetime.now().timestamp()
    if _GEMINI_GROUNDING_UNAVAILABLE_UNTIL and now < _GEMINI_GROUNDING_UNAVAILABLE_UNTIL:
        return _wikipedia_research(subject, creative_brief)
    prompt = f"""Research a factual YouTube Short before it is written.

Subject: {subject}
Creative brief: {creative_brief or 'No additional brief.'}

Use Google Search. Return concise research notes, not a script. Identify one narrow story with a clear human stake and verify every date, number, name, causal claim, and scientific statement. Prefer primary or highly authoritative sources. If sources conflict, say so and exclude the disputed detail. Include enough context for a writer to avoid exaggeration or invented connective details."""
    request = {
        "chat_prompt": prompt,
        "system": "You are a meticulous fact-checking researcher. Never invent a source or fill a factual gap with a guess.",
        "temp": 0.2,
        "max_tokens": 2500,
        "remove_nl": False,
        "use_google_search": True,
        "return_metadata": True,
        "max_retries": 2,
    }
    try:
        notes, metadata = gpt_utils.llm_completion(**request)
    except Exception as primary_error:
        if "429" not in str(primary_error):
            raise
        fallback_model = os.getenv("GEMINI_RESEARCH_FALLBACK_MODEL", "gemini-2.5-flash-lite")
        try:
            notes, metadata = gpt_utils.llm_completion(**request, model=fallback_model)
        except Exception as fallback_error:
            _GEMINI_GROUNDING_UNAVAILABLE_UNTIL = datetime.now().timestamp() + 600
            try:
                return _wikipedia_research(subject, creative_brief)
            except Exception as wikipedia_error:
                raise Exception(
                    "Grounded research is temporarily unavailable from both Gemini Search and Wikimedia. "
                    "No unverified facts short was generated."
                ) from wikipedia_error

    sources = _normalize_sources(metadata.get("sources"))
    if not sources:
        return _wikipedia_research(subject, creative_brief)
    _GEMINI_GROUNDING_UNAVAILABLE_UNTIL = None
    return notes, sources


def _wikipedia_research(subject, creative_brief):
    """Build evidence notes from public Wikimedia APIs when Gemini Search is unavailable."""
    headers = {
        "User-Agent": "YouTubeShortsProductionStudio/1.0 (local creator research tool)",
        "Accept": "application/json",
    }
    date_match = re.search(
        r"\b(?:on|happened on)\s+([A-Z][a-z]+)\s+(\d{1,2})\b",
        str(subject),
    )
    if date_match:
        month = datetime.strptime(date_match.group(1), "%B").month
        day = int(date_match.group(2))
        url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{month:02d}/{day:02d}"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        events = response.json().get("events") or []
        if not events:
            raise Exception("Wikimedia returned no on-this-day events")

        notes = [f"Verified on-this-day candidates for {date_match.group(1)} {day}:"]
        sources = []
        seen_urls = set()
        for event in events[:18]:
            event_text = _clean_text(event.get("text"))
            year = event.get("year")
            if event_text:
                notes.append(f"- {year}: {event_text}")
            for page in event.get("pages") or []:
                content_urls = page.get("content_urls") or {}
                page_url = ((content_urls.get("desktop") or {}).get("page")) or ""
                if not page_url or page_url in seen_urls:
                    continue
                seen_urls.add(page_url)
                sources.append({
                    "title": _clean_text(page.get("normalizedtitle") or page.get("title")) or page_url,
                    "url": page_url,
                })
                if len(sources) >= 10:
                    break
            if len(sources) >= 10:
                break
        if not sources:
            sources.append({"title": f"Wikipedia: {date_match.group(1)} {day}", "url": url})
        return "\n".join(notes), _normalize_sources(sources)

    query = _clean_text(creative_brief) or _clean_text(subject)
    stop_words = {
        "about", "after", "behind", "brief", "connect", "explain", "facts", "focus",
        "from", "into", "short", "shorts", "show", "story", "tell", "that", "their",
        "through", "using", "what", "when", "where", "which", "while", "with", "without",
    }
    keywords = [
        word
        for word in re.findall(r"[A-Za-z0-9'-]+", query.lower())
        if len(word) > 2 and word not in stop_words
    ]
    query = " ".join(dict.fromkeys(keywords))[:160]
    if not query:
        query = "counterintuitive everyday science discovery"

    api_url = "https://en.wikipedia.org/w/api.php"
    search_response = requests.get(
        api_url,
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 4,
            "format": "json",
            "utf8": 1,
        },
        headers=headers,
        timeout=30,
    )
    search_response.raise_for_status()
    search_results = (search_response.json().get("query") or {}).get("search") or []
    titles = [_clean_text(item.get("title")) for item in search_results if item.get("title")]
    if not titles:
        raise Exception(f"Wikimedia found no research pages for: {query}")

    page_response = requests.get(
        api_url,
        params={
            "action": "query",
            "prop": "extracts|info",
            "titles": "|".join(titles),
            "explaintext": 1,
            "exintro": 1,
            "exchars": 1800,
            "inprop": "url",
            "format": "json",
            "redirects": 1,
        },
        headers=headers,
        timeout=30,
    )
    page_response.raise_for_status()
    pages = (page_response.json().get("query") or {}).get("pages") or {}
    notes = [f"Wikimedia research results for: {query}"]
    sources = []
    for page in pages.values():
        title = _clean_text(page.get("title"))
        extract = _clean_text(page.get("extract"))
        page_url = _clean_text(page.get("fullurl"))
        if extract:
            notes.append(f"\n{title}: {extract}")
        if page_url:
            sources.append({"title": title or page_url, "url": page_url})
    if not sources or len("".join(notes)) < 150:
        raise Exception(f"Wikimedia research was insufficient for: {query}")
    return "\n".join(notes), _normalize_sources(sources)


def generate_facts_story_package(
    facts_type,
    num_images=0,
    creative_brief="",
    audience="General audience",
    tone="Cinematic and curious",
    creator_angle="Explain why this matters to viewers today",
    target_duration=50,
    quality_mode="Production",
):
    facts_type = _clean_text(facts_type)
    context = _today_history_context()
    if "historical" in facts_type.lower() or "history" in facts_type.lower():
        facts_type = (
            f"One true, verifiable historical event that happened on {context['month_day']} in any year. "
            f"Current date is {context['date_iso']}; use {context['month_day']} as the on-this-day hook, "
            "not the current year as the event year."
        )
    return _generate_story_package(
        short_type="facts",
        subject=facts_type,
        num_images=num_images,
        creative_brief=creative_brief,
        audience=audience,
        tone=tone,
        creator_angle=creator_angle,
        target_duration=target_duration,
        quality_mode=quality_mode,
    )


def generate_reddit_story_package(
    num_images=0,
    creative_brief="",
    audience="General audience",
    tone="Suspenseful storytime",
    creator_angle="Tell an original, emotionally honest story with a useful takeaway",
    target_duration=50,
    quality_mode="Production",
):
    return _generate_story_package(
        short_type="reddit",
        subject="an original fictionalized storytime confession or dilemma, not a copied or paraphrased real post",
        num_images=num_images,
        creative_brief=creative_brief,
        audience=audience,
        tone=tone,
        creator_angle=creator_angle,
        target_duration=target_duration,
        quality_mode=quality_mode,
    )


def _review_story_package(package, context, research_notes, recent_content, audit):
    prompt = f"""Act as the final senior editor for a monetizable YouTube Short.

CONTEXT
{json.dumps(context, ensure_ascii=False, indent=2)}

FACT-CHECKED RESEARCH (facts must stay within this evidence)
{research_notes or 'This is an original fictional story. Do not present it as a copied real post.'}

RECENT CHANNEL OUTPUT TO AVOID COPYING
{json.dumps([{'title': item['title'], 'hook': item['hook']} for item in recent_content], ensure_ascii=False, indent=2)}

DETERMINISTIC AUDIT
{json.dumps(audit, ensure_ascii=False, indent=2)}

DRAFT PACKAGE
{json.dumps(package, ensure_ascii=False, indent=2)}

Silently rewrite anything needed, then return the complete improved package and an honest scorecard.

Editorial bar:
- The first sentence earns attention immediately through specific stakes, tension, novelty, or a surprising consequence—not generic clickbait.
- Every sentence either advances the story, deepens the stakes, supplies essential evidence, or delivers payoff.
- The turn or reveal is fair and understandable. The ending fully resolves the central promise.
- The narration sounds conversational when read aloud. Vary sentence lengths and remove filler, throat-clearing, clichés, and repeated ideas.
- Keep the exact requested word range. No sequel bait, fake quotations, unverifiable precision, or exaggerated causal claims.
- Make the substance and hook materially different from recent channel output.
- Preserve or improve image/SFX anchors so each is an exact phrase copied from the final script.
- Keep music_direction aligned to the emotional arc of the final script; it must describe instrumental underscore that will not compete with narration.
- Facts must remain inside the supplied research. Fiction must be clearly original and must not imply it is a verbatim real Reddit post.
- Keep it advertiser-friendly and avoid graphic details, hate, sexual content, dangerous instructions, or sensational treatment of tragedy.
- The title is under 100 characters, accurate, specific, and intriguing. The description is useful and includes #Shorts.
- Approve only if the result is genuinely ready for a human creator's final review."""
    result = gpt_utils.llm_completion(
        chat_prompt=prompt,
        system="You are a demanding short-form editor. Return only JSON matching the supplied schema.",
        temp=0.55,
        max_tokens=5000,
        remove_nl=False,
        response_schema=REVIEWED_PACKAGE_SCHEMA,
    )
    return _extract_json_object(result)


def _generate_story_package(
    short_type,
    subject,
    num_images=0,
    creative_brief="",
    audience="General audience",
    tone="Cinematic and curious",
    creator_angle="Explain why this matters to viewers today",
    target_duration=50,
    quality_mode="Production",
):
    num_images = max(0, min(int(num_images or 0), 25))
    target_duration = max(30, min(int(target_duration or 50), 58))
    min_words, max_words = _target_word_range(target_duration)
    recent_content = _recent_content()
    visual_style = get_visual_style_prompt()
    research_notes = ""
    research_sources = []
    if short_type == "facts":
        research_notes, research_sources = _research_facts(subject, creative_brief)

    context = {
        "short_type": short_type,
        "subject": subject,
        "creative_brief": _clean_text(creative_brief) or "Choose the strongest narrow angle within the subject.",
        "target_audience": _clean_text(audience) or "General audience",
        "tone": _clean_text(tone) or "Cinematic and curious",
        "editorial_angle": _clean_text(creator_angle) or "Explain why this matters to viewers today",
        "target_duration_seconds": target_duration,
        "target_word_range": [min_words, max_words],
        "image_prompt_count": num_images,
        "max_sfx_cues": get_sfx_max_cues(),
    }
    recent_summary = [{"title": item["title"], "hook": item["hook"]} for item in recent_content]
    system = "You are a senior YouTube Shorts writer and visual director. Return only valid JSON matching the supplied schema."
    chat = f"""Create one production-ready short-form story package.

CREATIVE DIRECTION
{json.dumps(context, ensure_ascii=False, indent=2)}

FACT-CHECKED RESEARCH
{research_notes or 'This is an original fictional story. Do not copy, adapt, or claim to quote a real Reddit post.'}

RECENT CHANNEL OUTPUT (make this materially different)
{json.dumps(recent_summary, ensure_ascii=False, indent=2)}

Rules:
- Privately consider at least three hooks and use the strongest truthful one. Do not output the alternatives.
- Write {min_words} to {max_words} words of spoken narration only. No headings, markdown, stage directions, or camera directions.
- Tell one self-contained story with a clear setup, escalating pressure, meaningful turn, consequence, and resolved payoff.
- Open on specific tension or consequence in the first sentence. Avoid generic "Did you know," "Here are," and "You won't believe" hooks.
- No cliffhangers, "part two," engagement bait, or unresolved central conflict.
- Build curiosity through withheld context, not withheld resolution. Add a fresh micro-payoff or new question roughly every 8 to 12 seconds.
- Use concrete nouns and active verbs. Vary sentence length for natural voice performance.
- The final line must cash the opening promise and add a clear original takeaway or reflection.
- Facts: use only details supported by the research above. Never invent dialogue, thoughts, dates, numbers, causes, or quotes. Make one micro-documentary, not a list.
- Reddit: write a wholly original fictionalized scenario. The description must disclose "Original fictional story". Do not imitate a known post.
- Keep the content advertiser-friendly. Avoid graphic, sexual, hateful, dangerous, or exploitative framing.
- The title must be accurate, specific, intriguing, and under 100 characters. The description must add context and include #Shorts.
- originality_angle must state what makes this episode meaningfully distinct and valuable.
- Create exactly {num_images} image prompts. Each anchor_text is an exact 2-to-6-word phrase copied from the script.
- Every image prompt must specify subject consistency, action, setting, emotion, camera/framing, lighting, and this shared style: {visual_style}
- Images must contain no text, captions, logos, watermarks, gore, nudity, or identifiable living public figures.
- Add only sparse SFX cues for genuine turns, reveals, or explicitly described foley. Anchor each to an exact script phrase.
- Allowed SFX: {', '.join(sorted(ALLOWED_SFX))}.
- Direct one instrumental background track with music_direction. Match the script's dominant emotion and pacing, avoid vocals, and provide 2 to 5 concrete search terms suitable for a reusable-music library.
- For Reddit content, fill the Reddit card. For facts, use empty Reddit strings while keeping the required object shape."""

    result = gpt_utils.llm_completion(
        chat_prompt=chat,
        system=system,
        temp=0.85,
        remove_nl=False,
        max_tokens=5000,
        response_schema=STORY_PACKAGE_SCHEMA,
    )
    package = _normalize_package(_extract_json_object(result), num_images, research_sources)
    initial_audit = audit_story_package(package, target_duration, recent_content)

    reviewer_report = None
    review_error = None
    if str(quality_mode or "").lower().startswith("production"):
        try:
            reviewed = _review_story_package(package, context, research_notes, recent_content, initial_audit)
            package = _normalize_package(reviewed.get("package") or package, num_images, research_sources)
            reviewer_report = reviewed.get("quality_review") or None
        except Exception as error:
            review_error = f"Editorial review could not complete: {error}"

    final_audit = audit_story_package(package, target_duration, recent_content)
    if reviewer_report:
        reviewer_score = max(0, min(100, int(reviewer_report.get("overall_score") or 0)))
        final_audit["score"] = round(final_audit["score"] * 0.55 + reviewer_score * 0.45)
        final_audit["approved"] = final_audit["approved"] and bool(reviewer_report.get("approved")) and final_audit["score"] >= 75
        final_audit["editorial_review"] = reviewer_report
    if review_error:
        final_audit["warnings"].append(review_error)
    final_audit["mode"] = quality_mode
    final_audit["requires_human_review"] = True

    if str(quality_mode or "").lower().startswith("production") and final_audit.get("blocking"):
        raise Exception("Story package failed the production quality gate: " + " ".join(final_audit.get("issues") or []))

    package["quality_report"] = final_audit
    package["research_sources"] = research_sources
    package["generation_context"] = context
    return package
