import re

from app.config import QUERY_EXPANSION_MAX_TOKENS, QUERY_EXPANSION_SYSTEM_PROMPT, QUERY_EXPANSION_TEMPERATURE
from app.generation_service import generate

_PREAMBLE_RE = re.compile(
    r'^(tentu(\s+saja)?|baik|oke|ok|teks (ini |tersebut )?menyatakan|berdasarkan (teks|dokumen)|'
    r'dokumen (ini |tersebut )?menyebutkan|saya (dapat|bisa) membantu)[^\n.:]*[.:,]\s*',
    re.IGNORECASE,
)


def _clean_expansion(text):
    cleaned = text.strip().strip('"\'“”')
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _PREAMBLE_RE.sub("", cleaned).strip().strip('"\'“”')
    return cleaned


def expand_query(question, model_cfg):
    if model_cfg["system_role"]:
        messages = [
            {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
    else:
        messages = [{"role": "user", "content": f"{QUERY_EXPANSION_SYSTEM_PROMPT}\n\n{question}"}]

    raw = generate(
        model_cfg["ollama_name"],
        messages,
        repeat_penalty=model_cfg["repeat_penalty"],
        temperature=QUERY_EXPANSION_TEMPERATURE,
        num_predict=QUERY_EXPANSION_MAX_TOKENS,
    )
    expanded = _clean_expansion(raw)
    return [expanded] if expanded else []
