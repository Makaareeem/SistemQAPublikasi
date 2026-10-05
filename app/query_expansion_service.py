"""One search expansion, always searched alongside the original question."""
import re
import logging
import requests
from app.cache import TTLCache
from app.config import QUERY_EXPANSION_MAX_TOKENS, QUERY_EXPANSION_SYSTEM_PROMPT, QUERY_EXPANSION_TEMPERATURE, CACHE_TTL
from app.generation_service import generate
from app.inference_errors import InferenceError, MESSAGES

log = logging.getLogger(__name__)

_cache = TTLCache(128, CACHE_TTL)
_NUMBERS = re.compile(r"\d+(?:[.,]\d+)*")
_TERMS = (
    (r"\b(ipm|pembangunan manusia)\b", "Indeks Pembangunan Manusia IPM"),
    (r"\b(tpt|pengangguran)\b", "Tingkat Pengangguran Terbuka TPT"),
    (r"\b(tpak|partisipasi angkatan kerja)\b", "Tingkat Partisipasi Angkatan Kerja TPAK"),
    (r"\b(kemiskinan|penduduk miskin)\b", "kemiskinan persentase penduduk miskin garis kemiskinan"),
    (r"\b(ikps|penanganan stunting)\b", "Indeks Khusus Penanganan Stunting IKPS"),
    (r"\b(ipak|anti korupsi|antikorupsi)\b", "Indeks Perilaku Anti Korupsi IPAK"),
    (r"\b(lansia|lanjut usia)\b", "penduduk lanjut usia lansia"),
)

def _clean_expansion(text):
    text = re.sub(r"\x60{3}(?:\w+)?", "", text.strip())
    text = re.sub(r"^\s*(?:\d+[.)]\s*|[-*]\s*)", "", text)
    text = re.sub(r"^(?:hasil|query(?: perluasan)?|perluasan(?: query)?|pertanyaan)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:\d+[.)]\s*|[-*]\s*)", "", text)
    return " ".join(text.strip().strip('"').split())

def validate_expansion(question, expanded):
    if not expanded or expanded.casefold().rstrip("?. ") == question.casefold().rstrip("?. "):
        return "Model belum menambahkan istilah pencarian."
    if re.search(r"\bipm\b", question, re.I) and re.search(r"\bindikator pembangunan manusia\b", expanded, re.I):
        return "Kepanjangan IPM pada perluasan tidak tepat."
    if len(expanded) > 700:
        return "Perluasan terlalu panjang."
    if set(_NUMBERS.findall(expanded)) - set(_NUMBERS.findall(question)):
        return "Perluasan menambahkan angka atau periode yang tidak diminta."
    if re.search(r"berdasarkan (?:teks|dokumen)|teks.*menyatakan|tentu saja|saya .*membantu|sebesar\s+\d|adalah\s+\d", expanded, re.I):
        return "Perluasan berisi jawaban, bukan istilah pencarian."
    return None

def terminology_expansion(question):
    additions = [phrase for pattern, phrase in _TERMS
                 if re.search(pattern, question, re.I) and phrase.casefold() not in question.casefold()]
    return question.rstrip("?. ") + ". " + "; ".join(additions) if additions else ""

def expand_query_result(question, model_cfg, use_cache=True, strict=True, cancel=None):
    if cancel is not None and cancel.is_set():
        raise InterruptedError()
    key = (question.strip(), model_cfg["ollama_name"], QUERY_EXPANSION_SYSTEM_PROMPT,
           QUERY_EXPANSION_TEMPERATURE, strict)
    cached = _cache.get(key) if use_cache else None
    if cached is not None:
        return {**cached, "cache_hit": True}
    prompt = QUERY_EXPANSION_SYSTEM_PROMPT
    messages = ([{"role":"system","content":prompt},{"role":"user","content":question}]
                if model_cfg["system_role"] else [{"role":"user","content":f"{prompt}\n\nPertanyaan: {question}\nPerluasan:"}])
    raw, reason, failed = "", None, False
    try:
        raw = generate(model_cfg["ollama_name"], messages, repeat_penalty=model_cfg["repeat_penalty"],
                       temperature=QUERY_EXPANSION_TEMPERATURE, num_predict=QUERY_EXPANSION_MAX_TOKENS,
                       cancel=cancel)
    except InterruptedError:
        raise
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        failed = True
        reason = MESSAGES.get(getattr(exc, "code", ""), "Model belum berhasil membuat perluasan.")
        log.warning("Expansion failed model=%s type=%s code=%s", model_cfg["ollama_name"],
                    type(exc).__name__, getattr(exc, "code", "expansion_failed"), exc_info=True)
    if cancel is not None and cancel.is_set():
        raise InterruptedError()
    expanded = _clean_expansion(raw)
    reason = reason or validate_expansion(question, expanded)
    origin = "model"
    if reason and strict:
        expanded = terminology_expansion(question)
        origin = "terminology" if expanded else "original"
        reason += (" Digunakan perluasan istilah statistik." if expanded else " Pertanyaan asli tetap digunakan.")
    elif expanded and set(_NUMBERS.findall(question)) - set(_NUMBERS.findall(expanded)):
        expanded = question.rstrip("?. ") + ". " + expanded
    result = {"queries":[expanded] if expanded else [], "raw":raw, "reason":reason,
              "origin":origin, "cache_hit":False}
    if use_cache and not failed:
        _cache.put(key, result)
    return result

def expand_query(question, model_cfg):
    return expand_query_result(question, model_cfg)["queries"]
