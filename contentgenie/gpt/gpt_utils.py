import json
import os
import re
from time import sleep, time

import requests
import tiktoken
import yaml

from contentgenie.config.api_db import ApiKeyManager


def _safe_error_message(error, secret=None):
    message = str(error)
    if secret:
        message = message.replace(str(secret), "[REDACTED]")
    message = re.sub(r"([?&]key=)[^&\s]+", r"\1[REDACTED]", message, flags=re.IGNORECASE)
    return message


def num_tokens_from_messages(texts, model="gpt-4o-mini"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-4o-mini":  # note: future models may deviate from this
        if isinstance(texts, str):
            texts = [texts]
        score = 0
        for text in texts:
            score += 4 + len(encoding.encode(text))
        return score
    else:
        raise NotImplementedError(f"num_tokens_from_messages() is not presently implemented for model {model}.")


def extract_biggest_json(string):
    json_regex = r"\{(?:[^{}]|(?R))*\}"
    json_objects = re.findall(json_regex, string)
    if json_objects:
        return max(json_objects, key=len)
    return None


def get_first_number(string):
    pattern = r'\b(0|[1-9]|10)\b'
    match = re.search(pattern, string)
    if match:
        return int(match.group())
    else:
        return None


def load_yaml_file(file_path: str) -> dict:
    """Reads and returns the contents of a YAML file as dictionary"""
    return yaml.safe_load(open_file(file_path))


def load_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    return json_data

from pathlib import Path

def load_local_yaml_prompt(file_path):
    _here = Path(__file__).parent
    _absolute_path = (_here / '..' / file_path).resolve()
    json_template = load_yaml_file(str(_absolute_path))
    return json_template['chat_prompt'], json_template['system_prompt']


def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as infile:
        return infile.read()


def _gemini_messages(chat_prompt="", system="", conversation=None):
    system_parts = []
    contents = []
    messages = conversation or [
        {"role": "system", "content": system},
        {"role": "user", "content": chat_prompt}
    ]

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if not content:
            continue
        if role == "system":
            system_parts.append({"text": content})
        else:
            contents.append({
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}]
            })

    if not contents and chat_prompt:
        contents.append({"role": "user", "parts": [{"text": chat_prompt}]})

    payload = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def _extract_grounding_metadata(result):
    """Return a compact, serializable provenance record from a Gemini response."""
    sources = []
    queries = []
    seen_urls = set()
    candidates = result.get("candidates") or []
    for candidate in candidates:
        grounding = candidate.get("groundingMetadata") or {}
        queries.extend(grounding.get("webSearchQueries") or [])
        for chunk in grounding.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            url = str(web.get("uri") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append({
                "title": str(web.get("title") or url).strip(),
                "url": url,
            })

    return {
        "sources": sources,
        "web_search_queries": list(dict.fromkeys(str(query) for query in queries if query)),
        "usage": result.get("usageMetadata") or {},
        "finish_reason": candidates[0].get("finishReason") if candidates else None,
    }


def _gemini_completion(
    api_key,
    model,
    chat_prompt="",
    system="",
    temp=0.7,
    max_tokens=2000,
    conversation=None,
    response_schema=None,
    use_google_search=False,
    return_metadata=False,
):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = _gemini_messages(chat_prompt=chat_prompt, system=system, conversation=conversation)
    payload["generationConfig"] = {
        "temperature": temp,
        "maxOutputTokens": max_tokens,
    }
    if response_schema:
        payload["generationConfig"].update({
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        })
    if use_google_search:
        payload["tools"] = [{"google_search": {}}]

    timeout = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "120"))
    response = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()
    candidates = result.get("candidates") or []
    if not candidates:
        feedback = result.get("promptFeedback") or {}
        raise Exception(f"Gemini returned no candidates. Prompt feedback: {feedback}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise Exception(f"Gemini returned an empty response (finish reason: {candidates[0].get('finishReason')})")

    if return_metadata:
        metadata = _extract_grounding_metadata(result)
        metadata["model"] = model
        return text, metadata
    return text


def llm_completion(
    chat_prompt="",
    system="",
    temp=0.7,
    max_tokens=2000,
    remove_nl=True,
    conversation=None,
    response_schema=None,
    use_google_search=False,
    return_metadata=False,
    model=None,
    max_retries=5,
):
    gemini_key = ApiKeyManager.get_api_key("GEMINI_API_KEY")
    if not gemini_key:
        raise Exception("No Gemini API key found for LLM request")
    model = model or os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    max_retry = max(1, int(max_retries or 1))
    retry = 0
    error = ""
    for i in range(max_retry):
        try:
            completion = _gemini_completion(
                gemini_key,
                model=model,
                chat_prompt=chat_prompt,
                system=system,
                temp=temp,
                max_tokens=max_tokens,
                conversation=conversation,
                response_schema=response_schema,
                use_google_search=use_google_search,
                return_metadata=return_metadata,
            )
            if return_metadata:
                text, metadata = completion
            else:
                text = completion
                metadata = None
            if remove_nl:
                text = re.sub(r'\s+', ' ', text)
            filename = '%s_llm_completion.txt' % time()
            if not os.path.exists('.logs/gpt_logs'):
                os.makedirs('.logs/gpt_logs')
            with open('.logs/gpt_logs/%s' % filename, 'w', encoding='utf-8') as outfile:
                outfile.write(f"System prompt: ===\n{system}\n===\n"+f"Chat prompt: ===\n{chat_prompt}\n===\n" + f'RESPONSE:\n====\n{text}\n===\n')
                if metadata:
                    outfile.write("METADATA:\n====\n" + json.dumps(metadata, indent=2, ensure_ascii=False) + "\n===\n")
            return (text, metadata) if return_metadata else text
        except Exception as oops:
            retry += 1
            error = _safe_error_message(oops, gemini_key)
            print('Error communicating with Gemini:', error)
            if retry < max_retry:
                sleep(min(2 ** retry, 12))
    raise Exception(f"Error communicating with LLM Endpoint Completion errored more than error: {error}")
