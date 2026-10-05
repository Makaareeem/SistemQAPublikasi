import math
import threading
import torch
from sentence_transformers import CrossEncoder
from app.device_policy import retrieval_device
from app.config import RERANKER_MODEL_ID, RERANKER_REVISION, RERANKER_DEVICE, RERANK_SCORE_THRESHOLD, RETRIEVAL_K

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            _model = CrossEncoder(RERANKER_MODEL_ID, revision=RERANKER_REVISION, device=retrieval_device(RERANKER_DEVICE))
    return _model


def rerank(question, docs, top_k=RETRIEVAL_K):
    if not 1 <= top_k <= 20:
        raise ValueError("top_k harus 1 sampai 20.")
    if not docs:
        return [], []
    scores = get_model().predict([[question, doc.page_content] for doc in docs],
                                 batch_size=20, show_progress_bar=False, activation_fct=torch.nn.Identity())
    ranked = sorted(((doc, float(score)) for doc, score in zip(docs, scores) if math.isfinite(float(score))),
                    key=lambda pair: pair[1], reverse=True)
    return [(doc, score) for doc, score in ranked if score >= RERANK_SCORE_THRESHOLD][:top_k], ranked
