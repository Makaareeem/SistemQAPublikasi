"""Application use-case shared by JSON and SSE adapters; no HTTP dependencies."""
import time
from app import retrieval_service as retrieval
from app.cache import TTLCache
from app.answer_stream import AnswerStream
from app.config import (CACHE_TTL, MODEL_REGISTRY, RERANK_SCORE_THRESHOLD,
                        RESPONSE_STYLES, OTHER_SOURCES_MAX, OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH, OLLAMA_NUM_GPU)
from app.query_expansion_service import expand_query_result
from app.reranker_service import rerank
from app.prompt_constructor import build_messages, fit_context
from app.generation_service import stream_generate
from app.inference_errors import InferenceError
from app.evidence import ABSTENTION, check_answer, source_excerpt

_rank_cache = TTLCache(128, CACHE_TTL)


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Permintaan dibatalkan.")


def run_pipeline(req, vectorstore, bm25, cancel=None, evaluation=False):
    started = time.perf_counter()
    cfg = MODEL_REGISTRY[req.model_key]
    timings = {"expansion_s": 0.0, "search_rerank_s": 0.0, "retrieval_s": 0.0,
               "generation_s": 0.0, "citation_s": 0.0, "first_token_s": None}  # citation_s retained for notebook compatibility
    process = {"original_query": req.question, "expanded_queries": [], "reranked": [],
               "rerank_threshold": RERANK_SCORE_THRESHOLD, "candidates_before_rerank": 0}
    cache = {"expansion": False, "search_rerank": False, "enabled": not evaluation}
    scored_docs, all_ranked, warnings = [], [], []
    if req.use_rag:
        _check_cancel(cancel)
        yield "expanding", {"label": "Memperluas pertanyaan..."}
        t = time.perf_counter()
        expansion = expand_query_result(req.question, cfg, use_cache=not evaluation,
                                         strict=getattr(req, "strict_expansion", True), cancel=cancel)
        timings["expansion_s"] = time.perf_counter() - t
        cache["expansion"] = expansion["cache_hit"]
        process.update(expanded_queries=expansion["queries"], expansion_raw=expansion["raw"],
                       expansion_note=expansion["reason"], expansion_origin=expansion.get("origin", "model"))
        yield "expanded", {"label": "Perluasan selesai; pertanyaan asli tetap digunakan.", "process": dict(process)}
        _check_cancel(cancel)
        yield "retrieving", {"label": "Mencari dan mengurutkan sumber..."}
        t = time.perf_counter()
        queries = [req.question] + expansion["queries"]
        key = (retrieval.KB_FINGERPRINT, req.question, tuple(queries), req.top_k, RERANK_SCORE_THRESHOLD)
        ranked = _rank_cache.get(key) if not evaluation else None
        if ranked is None:
            candidates = retrieval.hybrid_search(vectorstore, bm25, queries, use_cache=not evaluation)
            _check_cancel(cancel)
            scored_docs, all_ranked = rerank(req.question, candidates, top_k=req.top_k)
            ranked = (scored_docs, all_ranked, len(candidates))
            if not evaluation:
                _rank_cache.put(key, ranked)
        else:
            cache["search_rerank"] = True
        _check_cancel(cancel)
        scored_docs, all_ranked, count = ranked
        eligible = [(d, s) for d, s in all_ranked if s >= RERANK_SCORE_THRESHOLD]
        fitted = fit_context(req.question, eligible, cfg["system_role"], req.response_style, max_sources=req.top_k)
        if eligible and not fitted:
            raise InferenceError("context_unavailable", "No eligible whole chunk fits context")
        if [d.metadata["faiss_id"] for d, _ in fitted] != [d.metadata["faiss_id"] for d, _ in scored_docs]:
            warnings.append("Sebagian sumber tidak masuk karena batas konteks; isi sumber tidak dipotong.")
        scored_docs = fitted
        selected = {d.metadata["faiss_id"] for d, _ in scored_docs}
        process.update(candidates_before_rerank=count, selected_count=len(scored_docs),
                       reranked=[{**retrieval.format_source(d, s), "passed": s >= RERANK_SCORE_THRESHOLD,
                                  "selected": d.metadata["faiss_id"] in selected} for d, s in all_ranked])
        timings["search_rerank_s"] = time.perf_counter() - t
        timings["retrieval_s"] = timings["expansion_s"] + timings["search_rerank_s"]
        yield "reranked", {"label": f"{len(scored_docs)} sumber digunakan dari {count} kandidat.", "process": process}
    docs = [doc for doc, _ in scored_docs]
    sources = [{**retrieval.format_source(d, s), "index": i, "answer": "",
                "quote": source_excerpt(req.question, d.page_content), "source_text": d.page_content, "citation_status": "excerpt_only"}
               for i, (d, s) in enumerate(scored_docs, 1)]
    if sources:
        yield "sources", {"sources": sources}
    metrics, answer, answer_status = {}, "", "no_evidence"
    if req.use_rag and not docs:
        answer = ABSTENTION
        # No answer generation without evidence.
        yield "answer", {"answer": answer, "status": answer_status, "warnings": warnings}
    else:
        _check_cancel(cancel)
        yield "generating", {"label": "Menyusun jawaban..."}
        messages = build_messages(req.question, docs, cfg["system_role"], req.use_rag, req.response_style)
        t = time.perf_counter()
        output = AnswerStream(RESPONSE_STYLES[req.response_style]["max_new_tokens"])
        stream = stream_generate(cfg["ollama_name"], messages, repeat_penalty=cfg["repeat_penalty"],
                                 num_predict=RESPONSE_STYLES[req.response_style]["max_new_tokens"], cancel=cancel)
        try:
            for part in stream:
                _check_cancel(cancel)
                if "text" in part:
                    if timings["first_token_s"] is None and part["text"]:
                        timings["first_token_s"] = time.perf_counter() - started
                    text = output.push(part["text"])
                    if text:
                        yield "token", {"text": text, "provisional": True}
                if "metrics" in part:
                    metrics = part["metrics"]
                if output.stopped:
                    break
        finally:
            # Closing the generator also closes the underlying HTTP response, including on cancel/error.
            close = getattr(stream, "close", None)
            if close:
                close()
        _check_cancel(cancel)
        timings["generation_s"] = time.perf_counter() - t
        provider_metrics_available = bool(metrics)
        answer, finish = output.finish(metrics.get("done_reason"))
        metrics = {**metrics, **finish, "provider_metrics_available": provider_metrics_available}
        issues = check_answer(answer, docs, question=req.question) if req.use_rag else []
        if finish["trimmed_incomplete_sentence"]:
            issues.append("Batas panjang tercapai; bagian kalimat yang belum selesai tidak ditampilkan.")
        if not answer.strip() and not req.use_rag:
            raise InferenceError("model_incomplete_response" if finish["output_finish_reason"] == "token_limit_no_sentence"
                                 else "model_empty_response", "No complete non-RAG answer")
        if not answer.strip():
            answer = "Bagian sumber yang paling dekat dengan pertanyaan:\n\n" + "\n\n".join(
                f"{source_excerpt(req.question, d.page_content)} [{i}]" for i,d in enumerate(docs[:3],1))
            issues.append("Model belum menghasilkan ringkasan; cuplikan sumber ditampilkan.")
        warnings.extend(issues)
        if issues and req.use_rag:
            answer_status = "needs_review"
        else:
            answer_status = "basic_checks_passed" if req.use_rag else "non_rag"
        yield "answer", {"answer": answer, "status": answer_status, "warnings": warnings}
    def publication_key(doc):
        source = retrieval.format_source(doc, 0)
        return source["bps_url"] or (source["document_title"], source["document_year"])

    used_publications = {publication_key(d) for d in docs}
    other = []
    for doc, score in all_ranked:
        identity = publication_key(doc)
        if score >= RERANK_SCORE_THRESHOLD and identity not in used_publications:
            other.append(retrieval.format_source(doc, score))
            used_publications.add(identity)
        if len(other) >= OTHER_SOURCES_MAX:
            break
    _check_cancel(cancel)
    timings["processing_s"] = time.perf_counter() - started
    payload = {"answer": answer, "answer_status": answer_status, "sources": sources, "other_sources": other,
               "warnings": warnings, "latency": {k: round(v, 3) if v is not None else None for k, v in timings.items()},
               "config": {"model_key": req.model_key, "use_rag": req.use_rag,
                          "response_style": req.response_style, "num_ctx": OLLAMA_NUM_CTX, "num_batch": OLLAMA_NUM_BATCH, "num_gpu": OLLAMA_NUM_GPU,
                          "kb_fingerprint": retrieval.KB_FINGERPRINT,
                          "threshold": RERANK_SCORE_THRESHOLD, "evaluation": evaluation},
               "cache": cache, "generation_metrics": metrics, "process": process}
    if evaluation:
        payload["contexts"] = [d.page_content for d in docs]
    yield "done", payload
