"""Regression suite with fake inference: no Ollama, downloads or GPU required."""
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from pydantic import ValidationError
from app import main, pipeline, query_expansion_service as expansion, retrieval_service as retrieval
from app.cache import TTLCache
from app.config import MODEL_REGISTRY, DEFAULT_MODEL_KEY
from app.evidence import check_answer, UNVERIFIED
from app.prompt_constructor import build_messages, fit_context
from app.reranker_service import rerank
from app.schemas import AskRequest, EvaluationRequest

CFG = MODEL_REGISTRY[DEFAULT_MODEL_KEY]

def doc(text="Kemiskinan tahun 2024 sebesar 9,03 persen.", idx=0, **metadata):
    return Document(page_content=text, metadata={"faiss_id": idx, "source_id": f"faiss:{idx}",
        "chunk_id": "legacy-duplicate", "document_title": "Publikasi", "document_year": "2025",
        "bps_url": f"https://www.bps.go.id/{idx}", **metadata})

class CoreTests(unittest.TestCase):
    def test_threshold_is_real(self):
        model = SimpleNamespace(predict=lambda *a, **k: [-8, 2, -9])
        with patch("app.reranker_service.get_model", return_value=model):
            chosen, ranked = rerank("Q", [doc(idx=i) for i in range(3)])
        self.assertEqual([s for _, s in chosen], [2])
        self.assertEqual(len(ranked), 3)

    def test_non_rag_prompt(self):
        for system_role in (True, False):
            messages = build_messages("Q", [], system_role, use_rag=False)
            text = " ".join(m["content"] for m in messages)
            self.assertNotIn("berdasarkan SUMBER", text)
            self.assertNotIn("sertakan sitasi", text)

    def test_input_validation(self):
        for args in ({"question": " "}, {"question": "Q", "top_k": -1},
                     {"question": "Q", "top_k": 99}, {"question": "Q", "use_rag": False},
                     {"question": "Q", "response_style": "unknown"}):
            with self.assertRaises(ValidationError):
                AskRequest(**args)
        self.assertFalse(EvaluationRequest(question="Q", use_rag=False).use_rag)

    def test_source_identity_pages_and_url(self):
        source = retrieval.format_source(doc(page_start=2, page_end=None,
                  chunk_page_start=9, chunk_page_end=10), 2)
        self.assertEqual((source["page_start"], source["page_end"]), (9,10))
        self.assertEqual(source["source_id"], "faiss:0")
        bad = doc(); bad.metadata["bps_url"] = "javascript:alert(1)"
        self.assertIsNone(retrieval.format_source(bad, 2)["bps_url"])

    def test_expansion_validation(self):
        self.assertIsNotNone(expansion.validate_expansion("kemiskinan 2024", "kemiskinan 2024 sebesar 9,82 persen"))
        self.assertIsNone(expansion.validate_expansion("kemiskinan 2024", "kemiskinan"))
        self.assertIsNone(expansion.validate_expansion("kemiskinan 2024", "Data kemiskinan tahun 2024"))
        with patch.object(expansion, "generate", return_value="Data kemiskinan tahun 2024") as generate:
            expansion._cache.clear()
            expansion.expand_query_result("kemiskinan 2024", CFG)
            result = expansion.expand_query_result("kemiskinan 2024", CFG)
            self.assertTrue(result["cache_hit"])
            self.assertEqual(generate.call_count, 1)
            expansion.expand_query_result("kemiskinan 2024", CFG, use_cache=False)
            self.assertEqual(generate.call_count, 2)

    def test_cache_bounds_and_ttl(self):
        c = TTLCache(1, 2)
        with patch("app.cache.monotonic", return_value=0): c.put("a", [1])
        with patch("app.cache.monotonic", return_value=1):
            value = c.get("a"); value.append(2); self.assertEqual(c.get("a"), [1])
            c.put("b", [2]); self.assertIsNone(c.get("a"))
        with patch("app.cache.monotonic", return_value=4): self.assertIsNone(c.get("b"))

    def test_answer_checks(self):
        self.assertEqual(check_answer("Pada 2024 sebesar 9,03 persen [1].", [doc()]), [])
        self.assertTrue(check_answer("Pada 2024 sebesar 99 persen [1].", [doc()]))
        self.assertTrue(check_answer("Angka 9,03 persen [9].", [doc()]))
        self.assertTrue(check_answer("Angka 9,03 persen [1].", [doc("Target 2024 sebesar 9,03 persen.")]))
        self.assertEqual(check_answer("Target 2024 sebesar 9,03 persen [1].", [doc("Target 2024 sebesar 9,03 persen.")]), [])

    def test_fit_context_preserves_whole_chunks(self):
        docs = [(doc("x" * 20000), 3), (doc(), 2)]
        selected = fit_context("kemiskinan", docs, True, "detail")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][0].page_content, docs[1][0].page_content)

    def test_batch_embedding_and_dedup(self):
        import numpy as np
        embeddings = retrieval.NomicQueryEmbeddings.__new__(retrieval.NomicQueryEmbeddings)
        calls = []
        embeddings.model = SimpleNamespace(encode=lambda texts, **kw: calls.append(texts) or np.array([[1., 0.] for _ in texts]))
        vectors = embeddings.embed_queries(["A", "B", "A"], use_cache=False)
        self.assertEqual(len(calls), 1); self.assertEqual(len(calls[0]), 2); self.assertEqual(len(vectors), 3)
        self.assertEqual(retrieval.tokenize("TPAK, tpak?"), ["tpak", "tpak"])

class PipelineTests(unittest.TestCase):
    def setUp(self):
        pipeline._rank_cache.clear()
        self.patches = [
            patch.object(pipeline, "expand_query_result", return_value={"queries":["perluasan"],"raw":"perluasan","reason":None,"cache_hit":False}),
            patch.object(retrieval, "hybrid_search", return_value=[doc()]),
            patch.object(pipeline, "rerank", return_value=([(doc(),2)],[(doc(),2)])),
            patch.object(pipeline, "stream_generate", return_value=iter([{"text":"Pada 2024 sebesar 9,03 persen [1]."},{"metrics":{"done_reason":"stop"}}])),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def test_sources_are_literal_and_no_summary_stage_runs(self):
        events = list(pipeline.run_pipeline(AskRequest(question="kemiskinan 2024"), None, None))
        stages = [s for s,_ in events]
        self.assertNotIn("citing", stages)
        self.assertEqual(stages.count("sources"), 1)
        self.assertLess(stages.index("sources"), stages.index("token"))
        self.assertEqual(events[-1][1]["latency"]["citation_s"], 0.0)
        self.assertEqual(events[-1][1]["sources"][0]["answer"], "")
        self.assertIn(events[-1][1]["sources"][0]["quote"], doc().page_content)
        self.assertEqual(events[-1][1]["sources"][0]["citation_status"], "excerpt_only")
        self.mocks[0].assert_called_once()
        self.mocks[3].assert_called_once()
        self.assertEqual(self.mocks[1].call_args.args[2], ["kemiskinan 2024", "perluasan"])
        self.assertEqual(events[-1][1]["answer_status"], "basic_checks_passed")

    def test_no_evidence_skips_answer_generation(self):
        self.mocks[2].return_value = ([], [(doc(), -9)])
        events = list(pipeline.run_pipeline(AskRequest(question="Q"), None, None))
        self.assertEqual(events[-1][1]["answer_status"], "no_evidence")
        self.mocks[3].assert_not_called()

    def test_eval_bypasses_cache_and_returns_exact_context(self):
        events = list(pipeline.run_pipeline(EvaluationRequest(question="Q"), None, None, evaluation=True))
        self.assertFalse(self.mocks[0].call_args.kwargs["use_cache"])
        self.assertFalse(self.mocks[1].call_args.kwargs["use_cache"])
        self.assertEqual(events[-1][1]["contexts"], [doc().page_content])

    def test_answer_retained_with_review_warning(self):
        self.mocks[3].return_value = iter([{"text":"Pada 2024 sebesar 99 persen [1]."}])
        result = list(pipeline.run_pipeline(AskRequest(question="Q"), None, None))[-1][1]
        self.assertIn("99 persen", result["answer"])
        self.assertEqual(result["answer_status"], "needs_review")
        self.assertTrue(result["warnings"])

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.runner = main.JobRunner()
        self.jobs_patch = patch.object(main, "jobs", self.runner); self.jobs_patch.start()
        self.ready_patch = patch.dict(main._resources, ready=True); self.ready_patch.start()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close); self.addCleanup(self.runner.close)
        self.addCleanup(self.jobs_patch.stop); self.addCleanup(self.ready_patch.stop)

    def fake_pipeline(self, *a, **kw):
        yield "expanded", {"label":"ok", "process":{"expanded_queries":["Q"]}}
        yield "token", {"text":"Teks"}
        yield "done", {"answer":"Teks","answer_status":"basic_checks_passed",
                       "latency":{"first_token_s":0.01},"sources":[]}

    def test_public_nonrag_rejected_and_eval_disabled(self):
        self.assertEqual(self.client.post("/api/ask", json={"question":"IPM","use_rag":False}).status_code,422)
        with patch.object(main,"ENABLE_EVALUATION_API",False):
            self.assertEqual(self.client.post("/api/eval/ask", json={"question":"IPM"}).status_code,404)

    def test_json_and_sse_contract(self):
        with patch.object(main, "run_pipeline", side_effect=self.fake_pipeline):
            plain = self.client.post("/api/ask",json={"question":"IPM"})
            stream = self.client.post("/api/ask/stream",json={"question":"IPM"})
        self.assertEqual(plain.status_code,200)
        self.assertIn("queue_s",plain.json()["latency"])
        self.assertIn("event: token",stream.text); self.assertIn("event: done",stream.text)
        self.assertEqual(stream.headers["x-accel-buffering"],"no")

    def test_evaluation_key(self):
        with patch.object(main,"ENABLE_EVALUATION_API",True), patch.object(main,"EVALUATION_API_KEY","a"*32):
            self.assertEqual(self.client.post("/api/eval/ask",json={"question":"IPM"}).status_code,401)
            with patch.object(main,"run_pipeline",side_effect=self.fake_pipeline) as run:
                response=self.client.post("/api/eval/ask",json={"question":"IPM","use_rag":False},headers={"X-Evaluation-Key":"a"*32})
                self.assertEqual(response.status_code,200)
                self.assertTrue(run.call_args.kwargs["evaluation"])

    def test_queue_full(self):
        while self.runner.admission.acquire(blocking=False): pass
        response = self.client.post("/api/ask/stream", json={"question":"IPM"})
        self.assertEqual(response.status_code,429)

    def test_pipeline_error_sse(self):
        def failure(*args, **kwargs):
            yield "generating", {"label":"Mulai"}
            raise ValueError("simulated")
        with patch.object(main,"run_pipeline",side_effect=failure):
            response=self.client.post("/api/ask/stream",json={"question":"IPM"})
        self.assertIn("event: error",response.text)
        self.assertNotIn("simulated",response.text)


class QueueCancellationTests(unittest.TestCase):
    def test_cancelled_active_job_holds_slot_until_worker_stops(self):
        started, release = threading.Event(), threading.Event()
        def slow_pipeline(*args, **kwargs):
            started.set()
            release.wait(2)
            if False:
                yield
        with patch.object(main, "QUEUE_CONCURRENCY", 1), patch.object(main, "MAX_QUEUE", 1):
            runner = main.JobRunner()
        try:
            with patch.object(main, "run_pipeline", side_effect=slow_pipeline):
                events, cancel = runner.submit(AskRequest(question="Q"))
                self.assertTrue(started.wait(1))
                cancel.set()
                self.assertFalse(runner.active.acquire(blocking=False))
                release.set()
                self.assertTrue(runner.active.acquire(timeout=2))
                runner.active.release()
        finally:
            release.set()
            runner.close()

class TransportTests(unittest.TestCase):
    def test_keepalive_context_and_early_tokens(self):
        from app import generation_service as generation
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_lines.return_value = [
            b'{"message":{"content":"one "},"done":false}',
            b'{"message":{"content":"two"},"done":false}',
            b'{"done":true,"eval_count":2,"done_reason":"stop"}']
        session = MagicMock(); session.post.return_value = response
        with patch.object(generation, "_session", return_value=session):
            output = list(generation.stream_generate("mock", []))
        self.assertEqual(output[0]["text"], "one ")
        self.assertEqual(output[-1]["metrics"]["eval_count"], 2)
        payload = session.post.call_args.kwargs["json"]
        self.assertTrue(payload["stream"])
        self.assertIn("keep_alive", payload); self.assertIn("num_ctx", payload["options"])
        response.__exit__.assert_called_once()

    def test_broken_model_stream_is_not_success(self):
        from app import generation_service as generation
        from unittest.mock import MagicMock
        response = MagicMock(); response.__enter__.return_value = response
        response.iter_lines.return_value = [b'{"message":{"content":"partial"}}']
        session = MagicMock(); session.post.return_value = response
        with patch.object(generation, "_session", return_value=session):
            with self.assertRaises(RuntimeError):
                list(generation.stream_generate("mock", []))

    def test_mixed_actual_and_target_not_blanket_rejected(self):
        evidence = doc("Realisasi 2024 sebesar 9,03 persen. Target 2025 sebesar 7 persen.")
        self.assertEqual(check_answer("Pada 2024 sebesar 9,03 persen [1].", [evidence]), [])
        self.assertTrue(check_answer("Pada 2025 sebesar 7 persen [1].", [evidence]))


if __name__ == "__main__":
    unittest.main()
