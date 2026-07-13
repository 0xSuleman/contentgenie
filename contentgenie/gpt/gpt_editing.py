from contentgenie.gpt import gpt_utils
import json
import re

from contentgenie.config.render_settings import get_image_display_duration


def _normalize_words(text):
    return re.findall(r"[a-z0-9']+", str(text).lower())


def find_anchor_time(anchor_text, timed_words, allow_first_word_fallback=True):
    anchor_words = _normalize_words(anchor_text)
    if not anchor_words or not timed_words:
        return None
    words = [_normalize_words(word)[0] for _, word in timed_words if _normalize_words(word)]
    for start_index in range(0, max(len(words) - len(anchor_words) + 1, 0)):
        if words[start_index:start_index + len(anchor_words)] == anchor_words:
            return timed_words[start_index][0][0]
    if not allow_first_word_fallback:
        return None
    for start_index, word in enumerate(words):
        if anchor_words[0] == word:
            return timed_words[start_index][0][0]
    return None


def _find_anchor_time(anchor_text, timed_words):
    return find_anchor_time(anchor_text, timed_words, allow_first_word_fallback=True)


def assignImagePromptsToCaptions(captions, image_prompts, timed_words=None, n=15):
    prompt_items = []
    for item in image_prompts or []:
        if isinstance(item, dict):
            prompt = str(item.get("prompt") or item.get("visual_prompt") or item.get("scene") or item.get("query") or "").strip()
            anchor_text = str(item.get("anchor_text") or item.get("anchor") or item.get("spoken_anchor") or "").strip()
        else:
            prompt = str(item).strip()
            anchor_text = ""
        if prompt:
            prompt_items.append({"prompt": prompt, "anchor_text": anchor_text})
    image_prompts = prompt_items
    if not captions or not image_prompts:
        return []

    n = min(int(n or len(image_prompts)), len(image_prompts))
    image_prompts = image_prompts[:n]
    display_duration = get_image_display_duration()
    end_audio = captions[-1][0][1]
    usable_start = captions[0][0][0]
    usable_end = max(usable_start, end_audio - display_duration)

    pairs = []
    for index, item in enumerate(image_prompts):
        start = _find_anchor_time(item["anchor_text"], timed_words or [])
        if start is None:
            start = usable_start if n == 1 else usable_start + (usable_end - usable_start) * index / (n - 1)
        end = min(start + display_duration, end_audio)
        if end > start:
            pairs.append(((start, end), item["prompt"]))
    return pairs


def extractJsonFromString(text):
    start = text.find('{') 
    end = text.rfind('}') + 1
    if start == -1 or end == 0:
        raise Exception("Error: No JSON object found in response")
    json_str = text[start:end]
    return json.loads(json_str)


def getImageQueryPairs(captions, n=15, maxTime=2):
    chat, _ = gpt_utils.load_local_yaml_prompt('prompt_templates/editing_generate_images.yaml')
    prompt = chat.replace('<<CAPTIONS TIMED>>', f"{captions}").replace("<<NUMBER>>", f"{n}")
    
    try:
        # Get response and parse JSON
        res = gpt_utils.llm_completion(chat_prompt=prompt)
        data = extractJsonFromString(res)
        # Convert to pairs with time ranges
        pairs = []
        end_audio = captions[-1][0][1]
        
        for i, item in enumerate(data["image_queries"]):
            time = item["timestamp"]
            query = item["query"]
            
            # Skip invalid timestamps
            if time <= 0 or time >= end_audio:
                continue
                
            # Calculate end time for this image
            if i < len(data["image_queries"]) - 1:
                next_time = data["image_queries"][i + 1]["timestamp"]
                end = min(time + maxTime, next_time)
            else:
                end = min(time + maxTime, end_audio)
                
            pairs.append(((time, end), query + " image"))
            
        return pairs
        
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from LLM")
        return []
    except KeyError:
        print("Error: Malformed JSON structure")
        return []
    except Exception as e:
        print(f"Error processing image queries: {str(e)}")
        return []

def getVideoSearchQueriesTimed(captions_timed):
    """
    Generate timed video search queries based on caption timings.
    Returns list of [time_range, search_queries] pairs.
    """
    err = ""

    for _ in range(4):
        try:
            # Get total video duration from last caption
            end_time = captions_timed[-1][0][1]
            
            # Load and prepare prompt
            chat, system = gpt_utils.load_local_yaml_prompt('prompt_templates/editing_generate_videos.yaml')
            prompt = chat.replace("<<TIMED_CAPTIONS>>", f"{captions_timed}")
            
            # Get response and parse JSON
            res = gpt_utils.llm_completion(chat_prompt=prompt, system=system)
            data = extractJsonFromString(res)
            
            # Convert to expected format
            formatted_queries = []
            for segment in data["video_segments"]:
                time_range = segment["time_range"]
                queries = segment["queries"]
                
                # Validate time range
                if not (0 <= time_range[0] < time_range[1] <= end_time):
                    continue
                    
                # Ensure exactly 3 queries
                while len(queries) < 3:
                    queries.append(queries[-1])
                queries = queries[:3]
                
                formatted_queries.append([time_range, queries])
                
            # Verify coverage
            if not formatted_queries:
                raise ValueError("Generated segments don't cover full video duration")
                
            return formatted_queries
        except Exception as e:
            err = str(e)
            print(f"Error generating video search queries {err}")
    raise Exception(f"Failed to generate video search queries {err}")
