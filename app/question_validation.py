"""Conservative input checks, before queue admission; no model call or topic allowlist."""
import json
import re
import unicodedata
from pathlib import Path

RULES = json.loads((Path(__file__).resolve().parent.parent / "web" / "question-rules.json").read_text(encoding="utf-8"))
MESSAGES = RULES["messages"]
NON_TOPIC = frozenset(RULES["non_topic_words"])
NOISE = frozenset(RULES["noise_tokens"])


def question_issue(question):
    if not isinstance(question, str):
        return "question_invalid"
    if len(question.strip()) > RULES["max_length"]:
        return "question_too_long"
    # Ignore invisible formatting for inspection, without rewriting the user's query.
    text = "".join(c for c in question if unicodedata.category(c) != "Cf").strip()
    if not text:
        return "question_empty"
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\t\r\n" for c in text):
        return "question_invalid"
    tokens = re.findall(r"[^\W_]+", text.lower(), re.UNICODE)
    tokens = [token for token in tokens if any(c.isalpha() for c in token)]
    if not tokens:
        return "question_needs_topic"
    meaningful = [token for token in tokens if token not in NON_TOPIC]
    if not meaningful:
        return "question_needs_topic"
    # Only obvious noise. Do not reject unfamiliar acronyms, places or foreign words.
    if all(len(token) < 2 or token in NOISE or (len(token) >= 3 and len(set(token)) == 1)
           for token in meaningful):
        return "question_needs_topic"
    return None
