import json

import requests

from app.config import INFERENCE_URL, MAX_NEW_TOKENS


def generate(model_name, messages, repeat_penalty=1.0, temperature=0, num_predict=MAX_NEW_TOKENS, response_format=None):
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "repeat_penalty": repeat_penalty,
        },
    }
    if response_format:
        payload["format"] = response_format
    resp = requests.post(f"{INFERENCE_URL}/api/chat", json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def parse_json_response(raw, caller):
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"[{caller}] Gagal parse JSON dari model, output mentah:\n{raw}\n")
        return None


def health():
    try:
        requests.get(f"{INFERENCE_URL}/api/tags", timeout=5).raise_for_status()
        return True
    except requests.RequestException:
        return False
