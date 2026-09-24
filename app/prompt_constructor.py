from app.config import SYSTEM_PROMPT


def format_context(docs):
    blocks = []
    for i, doc in enumerate(docs, 1):
        header = f"[{i}] {doc.metadata.get('document_title', '-')}"
        if doc.metadata.get("section_id"):
            header += f" | {doc.metadata['section_id']}"
        blocks.append(f"{header}\n{doc.page_content}")
    return "\n\n".join(blocks)


def build_user_content(question, docs, use_rag):
    if use_rag and not docs:
        return (
            f"Pertanyaan: {question}\n\n"
            "(Tidak ditemukan bagian dokumen yang cukup relevan dengan pertanyaan ini.)"
        )
    if not docs:
        return f"Pertanyaan: {question}"
    return f"Konteks:\n{format_context(docs)}\n\nPertanyaan: {question}"


def build_messages(question, docs, system_role: bool, use_rag: bool = True):
    user_content = build_user_content(question, docs, use_rag)
    if system_role:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    return [{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{user_content}"}]
