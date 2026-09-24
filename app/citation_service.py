from app.config import CITATION_MAX_TOKENS, CITATION_SYSTEM_PROMPT
from app.generation_service import generate, parse_json_response


def generate_citations(question, docs, model_cfg):
    if not docs:
        return {}

    sources_block = "\n\n".join(f"[{i}] {doc.page_content}" for i, doc in enumerate(docs, 1))
    user_content = f"Pertanyaan: {question}\n\n{sources_block}"

    if model_cfg["system_role"]:
        messages = [
            {"role": "system", "content": CITATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    else:
        messages = [{"role": "user", "content": f"{CITATION_SYSTEM_PROMPT}\n\n{user_content}"}]

    raw = generate(
        model_cfg["ollama_name"],
        messages,
        repeat_penalty=model_cfg["repeat_penalty"],
        temperature=0,
        num_predict=CITATION_MAX_TOKENS,
        response_format="json",
    )

    data = parse_json_response(raw, "citation")
    if not isinstance(data, dict):
        return {}
    result = {}
    for item in data.get("sources", []):
        if not isinstance(item, dict) or "index" not in item or "answer" not in item:
            continue
        try:
            result[int(item["index"])] = item["answer"]
        except (ValueError, TypeError):
            continue
    return result
