from sentence_transformers import CrossEncoder

from app.config import RERANK_SCORE_THRESHOLD, RERANKER_MODEL_ID, RETRIEVAL_K

_model = None


def get_model():
    global _model
    if _model is None:
        _model = CrossEncoder(RERANKER_MODEL_ID)
    return _model


def rerank(question, docs, top_k=RETRIEVAL_K):
    if not docs:
        return [], []
    model = get_model()
    pairs = [[question, doc.page_content] for doc in docs]
    scores = model.predict(pairs)
    ranked = sorted(
        [(doc, float(score)) for doc, score in zip(docs, scores)],
        key=lambda pair: pair[1],
        reverse=True,
    )
    passed = [(doc, score) for doc, score in ranked if score >= RERANK_SCORE_THRESHOLD]
    return passed[:top_k], ranked
