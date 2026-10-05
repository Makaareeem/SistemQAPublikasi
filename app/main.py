"""HTTP adapters. Public endpoints always use RAG; evaluation is private and opt-in."""
import asyncio
import concurrent.futures
import hmac
import json
import logging
import queue
import threading
import time
import uuid
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from app.config import (ALLOWED_ORIGINS, ROOT_DIR, MODEL_REGISTRY, DEFAULT_MODEL_KEY,
                        QUEUE_CONCURRENCY, MAX_QUEUE, QUEUE_WAIT_TIMEOUT,
                        ENABLE_EVALUATION_API, EVALUATION_API_KEY)
from app.schemas import AskRequest, EvaluationRequest
from app.question_validation import question_issue, MESSAGES
from app.generation_service import model_status
from app.inference_errors import InferenceError, MESSAGES as INFERENCE_MESSAGES, provider_error
from app.retrieval_service import build_indices
from app.reranker_service import get_model
from app.pipeline import run_pipeline

log = logging.getLogger(__name__)
FRIENDLY_ERROR = "Pemrosesan gagal. Silakan coba kembali dan gunakan ID permintaan untuk pemeriksaan."
_resources = {"ready": False, "vectorstore": None, "bm25": None}


@asynccontextmanager
async def lifespan(app):
    global jobs
    if jobs.closed:
        jobs = JobRunner()
    _resources["ready"] = False
    try:
        _resources["vectorstore"], _resources["bm25"] = await asyncio.to_thread(build_indices)
        await asyncio.to_thread(get_model)  # Move weight loading out of the first user's request.
        _resources["ready"] = True
        yield
    finally:
        _resources["ready"] = False
        _resources["vectorstore"] = _resources["bm25"] = None
        jobs.close()


app = FastAPI(title="QA Publikasi BPS", version="0.2.0", lifespan=lifespan)
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Evaluation-Key"])


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    question_errors = {"string_too_short": "question_empty", "string_too_long": "question_too_long",
                       "string_type": "question_invalid", "missing": "question_empty"}
    for error in exc.errors():
        if error["loc"] == ("body", "question") and error["type"] in question_errors:
            code = question_errors[error["type"]]
            return JSONResponse(status_code=422, content={"detail": MESSAGES[code], "code": code})
    return JSONResponse(status_code=422, content={"detail": "Periksa pertanyaan dan pilihan Anda, lalu coba lagi.",
                                                "code": "invalid_request"})

def public_failure(exc):
    if isinstance(exc, InferenceError) and exc.code in INFERENCE_MESSAGES:
        return exc.code, INFERENCE_MESSAGES[exc.code]
    if isinstance(exc, MemoryError) or (isinstance(exc, RuntimeError) and provider_error(str(exc)).code == "model_memory"):
        return "model_memory", INFERENCE_MESSAGES["model_memory"]
    if isinstance(exc, requests.Timeout):
        return "model_timeout", "Model membutuhkan waktu terlalu lama. Silakan coba lagi dengan pertanyaan lebih spesifik."
    if isinstance(exc, requests.ConnectionError):
        return "model_unavailable", "Layanan jawaban belum dapat dihubungi. Silakan coba beberapa saat lagi."
    if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 404:
        return "model_missing", "Model yang dipilih belum tersedia. Silakan pilih model lain."
    return "processing_failed", FRIENDLY_ERROR


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
async def health():
    status = await asyncio.to_thread(model_status)
    actual = {name.removesuffix(":latest") for name in status["models"]}
    available = [key for key, cfg in MODEL_REGISTRY.items() if cfg["ollama_name"] in actual]
    return {"ready": _resources["ready"], "inference_reachable": status["reachable"],
            "available_models": available, "default_model": DEFAULT_MODEL_KEY}


@app.get("/api/ready")
async def readiness():
    status = await health()
    if not status["ready"] or not status["inference_reachable"] or DEFAULT_MODEL_KEY not in status["available_models"]:
        raise HTTPException(503, "Backend atau model default belum siap.")
    return {"ready": True}


class JobRunner:
    def __init__(self):
        self.closed = False
        self.cancellations = set()
        self.lock = threading.Lock()
        self.admission = threading.BoundedSemaphore(QUEUE_CONCURRENCY + MAX_QUEUE)
        self.active = threading.BoundedSemaphore(QUEUE_CONCURRENCY)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=QUEUE_CONCURRENCY + MAX_QUEUE)

    def close(self):
        with self.lock:
            self.closed = True
            for cancel in self.cancellations:
                cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def submit(self, req, evaluation=False):
        if self.closed:
            raise HTTPException(503, "Layanan sedang dihentikan. Coba beberapa saat lagi.")
        if not self.admission.acquire(blocking=False):
            raise HTTPException(429, "Antrean penuh. Silakan coba sebentar lagi.", headers={"Retry-After": "10"})
        events, cancel = queue.Queue(maxsize=128), threading.Event()
        request_id, created = uuid.uuid4().hex, time.perf_counter()
        with self.lock:
            if self.closed:
                self.admission.release()
                raise HTTPException(503, "Layanan sedang dihentikan. Coba beberapa saat lagi.")
            self.cancellations.add(cancel)

        def put(event):
            while not cancel.is_set():
                try:
                    events.put(event, timeout=0.25)
                    return True
                except queue.Full:
                    pass
            return False

        def worker():
            acquired, stage = False, "queued"
            try:
                put(("queued", {"label": "Menunggu giliran pemrosesan...", "request_id": request_id}))
                while not cancel.is_set():
                    acquired = self.active.acquire(timeout=0.25)
                    if acquired:
                        break
                    if time.perf_counter() - created >= QUEUE_WAIT_TIMEOUT:
                        put(("error", {"detail": INFERENCE_MESSAGES["queue_timeout"], "code": "queue_timeout", "request_id": request_id}))
                        return
                if not acquired or cancel.is_set():
                    return
                queued_s = time.perf_counter() - created
                for stage, payload in run_pipeline(req, _resources["vectorstore"], _resources["bm25"],
                                                   cancel=cancel, evaluation=evaluation):
                    if stage == "done":
                        payload["request_id"] = request_id
                        payload["latency"]["queue_s"] = round(queued_s, 3)
                        payload["latency"]["total_s"] = round(time.perf_counter() - created, 3)
                        if payload["latency"]["first_token_s"] is not None:
                            payload["latency"]["first_token_s"] = round(payload["latency"]["first_token_s"] + queued_s, 3)
                        log.info("request=%s model=%s total_s=%s status=%s", request_id, req.model_key,
                                 payload["latency"]["total_s"], payload["answer_status"])
                    if not put((stage, payload)):
                        break
            except InterruptedError:
                pass
            except Exception as exc:
                log.exception("Pipeline failed request=%s model=%s stage=%s", request_id, req.model_key, stage)
                code, message = public_failure(exc)
                put(("error", {"detail": message, "code": code, "request_id": request_id}))
            finally:
                if acquired:
                    self.active.release()
                self.admission.release()
                with self.lock:
                    self.cancellations.discard(cancel)
                put(("_end", {}))
        try:
            self.executor.submit(worker)
        except Exception:
            self.admission.release()
            with self.lock:
                self.cancellations.discard(cancel)
            raise
        return events, cancel

    async def events(self, request, req, evaluation=False):
        events, cancel = self.submit(req, evaluation)
        heartbeat = time.perf_counter()
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.to_thread(events.get, True, 1)
                except queue.Empty:
                    if time.perf_counter() - heartbeat >= 5:
                        heartbeat = time.perf_counter()
                        yield "heartbeat", {}
                    continue
                if event[0] == "_end":
                    return
                yield event
                if event[0] in ("done", "error"):
                    return
        finally:
            # A running Ollama call finishes/closes before the worker releases its slot.
            cancel.set()


jobs = JobRunner()


def validate(req):
    issue = question_issue(req.question)
    if issue:
        raise HTTPException(422, {"code": issue, "detail": MESSAGES[issue]})
    if req.model_key not in MODEL_REGISTRY:
        raise HTTPException(400, "Model tidak dikenal.")
    if not _resources["ready"]:
        raise HTTPException(503, "Indeks pencarian belum siap.")


@app.post("/api/ask")
async def ask(req: AskRequest, request: Request):
    validate(req)
    async for stage, payload in jobs.events(request, req):
        if stage == "error":
            raise HTTPException(503, payload)
        if stage == "done":
            return payload
    raise HTTPException(499, "Permintaan dibatalkan.")


@app.post("/api/ask/stream")
async def ask_stream(req: AskRequest, request: Request):
    validate(req)
    # Start admission before response headers so queue saturation produces HTTP 429.
    iterator = jobs.events(request, req)
    try:
        first = await anext(iterator)
    except StopAsyncIteration:
        raise HTTPException(499, "Permintaan dibatalkan.")

    async def body():
        try:
            yield f"event: {first[0]}\ndata: {json.dumps(first[1], ensure_ascii=False)}\n\n"
            async for stage, payload in iterator:
                yield f"event: {stage}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            await iterator.aclose()
    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.post("/api/eval/ask")
async def evaluate(req: EvaluationRequest, request: Request, x_evaluation_key: str = Header(default="")):
    if not ENABLE_EVALUATION_API:
        raise HTTPException(404, "Endpoint tidak tersedia.")
    if not hmac.compare_digest(x_evaluation_key, EVALUATION_API_KEY):
        raise HTTPException(401, "Kunci evaluasi tidak valid.")
    validate(req)
    async for stage, payload in jobs.events(request, req, evaluation=True):
        if stage == "error":
            raise HTTPException(503, payload)
        if stage == "done":
            return payload
    raise HTTPException(499, "Permintaan dibatalkan.")


app.mount("/", StaticFiles(directory=str(ROOT_DIR / "web"), html=True), name="static")
