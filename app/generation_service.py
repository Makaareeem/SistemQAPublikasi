"""Ollama transport: bounded timeouts, reusable connections and token streaming."""
import json
import logging
import threading
import requests
from app.inference_errors import InferenceError, provider_error, request_error
from app.config import INFERENCE_URL, MAX_NEW_TOKENS, OLLAMA_TIMEOUT, OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH, OLLAMA_NUM_GPU

log = logging.getLogger(__name__)
_local = threading.local()


def _session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _payload(model_name, messages, repeat_penalty, temperature, num_predict, response_format, stream):
    data = {
        "model": model_name, "messages": messages, "stream": stream,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": num_predict,
                    "repeat_penalty": repeat_penalty, "num_ctx": OLLAMA_NUM_CTX, "num_batch": OLLAMA_NUM_BATCH, "seed": 42},
    }
    if OLLAMA_NUM_GPU >= 0:
        data["options"]["num_gpu"] = OLLAMA_NUM_GPU
    if response_format is not None:
        data["format"] = response_format
    return data


def generate(model_name, messages, repeat_penalty=1.0, temperature=0,
             num_predict=MAX_NEW_TOKENS, response_format=None, metrics=None, cancel=None):
    parts = []
    for part in stream_generate(model_name, messages, repeat_penalty=repeat_penalty,
                                num_predict=num_predict, cancel=cancel, temperature=temperature,
                                response_format=response_format):
        if "text" in part:
            parts.append(part["text"])
        if metrics is not None and "metrics" in part:
            metrics.update(part["metrics"])
    return "".join(parts)


def _metrics(data):
    keys = ("load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count",
            "eval_duration", "total_duration", "done_reason")
    return {key: data[key] for key in keys if key in data}


def stream_generate(model_name, messages, repeat_penalty=1.0, num_predict=MAX_NEW_TOKENS,
                    cancel=None, temperature=0, response_format=None):
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Permintaan dibatalkan.")
    data = _payload(model_name, messages, repeat_penalty, temperature, num_predict, response_format, True)
    completed = False
    try:
        with _session().post(f"{INFERENCE_URL}/api/chat", json=data, stream=True,
                             timeout=(5, OLLAMA_TIMEOUT)) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                try:
                    payload = response.json()
                    diagnostic = payload.get("error", "") if isinstance(payload, dict) else ""
                except ValueError:
                    diagnostic = ""
                raise provider_error(diagnostic or f"HTTP {response.status_code}", response.status_code) from exc
            for line in response.iter_lines(chunk_size=1):
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("Permintaan dibatalkan.")
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    raise InferenceError("model_invalid_response", "Invalid stream JSON") from exc
                if not isinstance(item, dict):
                    raise InferenceError("model_invalid_response", "Stream item is not an object")
                if item.get("error"):
                    raise provider_error(item["error"])
                message = item.get("message", {})
                if not isinstance(message, dict):
                    raise InferenceError("model_invalid_response", "Invalid message object")
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise InferenceError("model_invalid_response", "Invalid content type")
                if content:
                    yield {"text": content}
                if item.get("done") is True:
                    completed = True
                    yield {"metrics": _metrics(item)}
                    break
    except requests.RequestException as exc:
        if cancel is not None and cancel.is_set():
            raise InterruptedError("Permintaan dibatalkan.") from exc
        raise request_error(exc) from exc
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Permintaan dibatalkan.")
    if not completed:
        raise InferenceError("model_stream_interrupted", "Stream ended without done")


def parse_json_response(raw, caller="model"):
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 and lines[-1].strip() == "```" else text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        log.warning("%s: format JSON tidak valid (output tidak dicatat).", caller)
        return None


def model_status():
    try:
        with _session().get(f"{INFERENCE_URL}/api/tags", timeout=(3, 5)) as response:
            response.raise_for_status()
            data = response.json()
        # Treat malformed health responses as unavailable, not as an adapter crash.
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            return {"reachable": False, "models": []}
        return {"reachable": True, "models": [m["name"] for m in data["models"]
                if isinstance(m, dict) and isinstance(m.get("name"), str)]}
    except (requests.RequestException, ValueError, KeyError):
        return {"reachable": False, "models": []}


def health():
    return model_status()["reachable"]
