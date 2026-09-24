import json
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.citation_service import generate_citations
from app.config import (
    ALLOWED_ORIGINS,
    DEFAULT_MODEL_KEY,
    MODEL_REGISTRY,
    QUEUE_CONCURRENCY,
    RERANK_SCORE_THRESHOLD,
    RETRIEVAL_K,
)
from app.generation_service import generate, health as generation_health
from app.prompt_constructor import build_messages
from app.query_expansion_service import expand_query
from app.reranker_service import rerank
from app.retrieval_service import build_indices, format_source, hybrid_search

app = FastAPI(title="QA Publikasi BPS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

vectorstore = None
bm25_retriever = None
_pipeline_semaphore = threading.Semaphore(QUEUE_CONCURRENCY)


@app.on_event("startup")
def startup():
    global vectorstore, bm25_retriever
    vectorstore, bm25_retriever = build_indices()


class AskRequest(BaseModel):
    question: str
    model_key: str = DEFAULT_MODEL_KEY
    use_rag: bool = True
    top_k: int = RETRIEVAL_K


@app.get("/api/health")
def health():
    return {
        "inference_reachable": generation_health(),
        "available_models": list(MODEL_REGISTRY.keys()),
        "default_model": DEFAULT_MODEL_KEY,
    }


def _validate(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Pertanyaan kosong")
    if req.model_key not in MODEL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"model_key tidak dikenal: {req.model_key}")


def _run_pipeline(req: AskRequest):
    model_cfg = MODEL_REGISTRY[req.model_key]
    t0 = time.perf_counter()

    scored_docs, all_ranked, expansions, num_candidates = [], [], [], 0
    if req.use_rag:
        yield "expanding", {"label": "Memperluas pertanyaan..."}
        expansions = expand_query(req.question, model_cfg)

        yield "retrieving", {"label": "Mencari kandidat (dense + BM25)..."}
        candidates = hybrid_search(vectorstore, bm25_retriever, [req.question] + expansions)
        num_candidates = len(candidates)

        yield "reranking", {"label": "Menyaring & mengurutkan sumber..."}
        scored_docs, all_ranked = rerank(req.question, candidates, top_k=req.top_k)

        process = {
            "expanded_queries": expansions,
            "candidates_before_rerank": num_candidates,
            "rerank_threshold": RERANK_SCORE_THRESHOLD,
            "reranked": [
                {
                    "document_title": doc.metadata.get("document_title"),
                    "chunk_id": doc.metadata.get("chunk_id"),
                    "score": round(score, 3),
                    "passed": score >= RERANK_SCORE_THRESHOLD,
                }
                for doc, score in all_ranked
            ],
        }
        yield "reranked", {
            "label": f"{len(scored_docs)} sumber lolos dari {num_candidates} kandidat",
            "process": process,
        }
    else:
        process = {"expanded_queries": [], "candidates_before_rerank": 0, "rerank_threshold": RERANK_SCORE_THRESHOLD, "reranked": []}
    docs = [doc for doc, _ in scored_docs]
    t_retrieval = time.perf_counter() - t0

    t1 = time.perf_counter()
    yield "citing", {"label": "Menyusun kutipan per sumber..."}
    citations = generate_citations(req.question, docs, model_cfg)
    t_citation = time.perf_counter() - t1

    t2 = time.perf_counter()
    yield "generating", {"label": f"Menyusun jawaban dengan {model_cfg['ollama_name']}..."}
    messages = build_messages(req.question, docs, system_role=model_cfg["system_role"], use_rag=req.use_rag)
    try:
        answer = generate(model_cfg["ollama_name"], messages, repeat_penalty=model_cfg["repeat_penalty"])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Inference gagal: {e}")
    t_generation = time.perf_counter() - t2

    sources = []
    for i, (doc, score) in enumerate(scored_docs, 1):
        src = format_source(doc, score)
        src["answer"] = citations.get(i, "")
        sources.append(src)

    yield "done", {
        "answer": answer,
        "sources": sources,
        "latency": {
            "retrieval_s": round(t_retrieval, 3),
            "citation_s": round(t_citation, 3),
            "generation_s": round(t_generation, 3),
            "total_s": round(time.perf_counter() - t0, 3),
        },
        "config": {"model_key": req.model_key, "use_rag": req.use_rag},
        "process": process,
    }


@app.post("/api/ask")
def ask(req: AskRequest):
    _validate(req)
    with _pipeline_semaphore:
        for stage, payload in _run_pipeline(req):
            if stage == "done":
                return payload


@app.post("/api/ask/stream")
def ask_stream(req: AskRequest):
    _validate(req)

    def event_gen():
        if not _pipeline_semaphore.acquire(blocking=False):
            yield f"event: queued\ndata: {json.dumps({'label': 'Server sedang memproses permintaan lain, menunggu giliran...'})}\n\n"
            _pipeline_semaphore.acquire(blocking=True)
        try:
            for stage, payload in _run_pipeline(req):
                yield f"event: {stage}\ndata: {json.dumps(payload)}\n\n"
        except HTTPException as e:
            yield f"event: error\ndata: {json.dumps({'detail': e.detail})}\n\n"
        finally:
            _pipeline_semaphore.release()

    return StreamingResponse(event_gen(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory="web", html=True), name="static")
