"""Regression coverage for failures missing from the original happy-path tests."""
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
import requests
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from app import main, generation_service as generation, query_expansion_service as expansion, pipeline, retrieval_service
from app.config import MODEL_REGISTRY, DEFAULT_MODEL_KEY
from app.evidence import check_answer, numbers
from app.inference_errors import InferenceError, provider_error
from app.schemas import AskRequest, EvaluationRequest

CFG = MODEL_REGISTRY[DEFAULT_MODEL_KEY]


def document(text="Kemiskinan 2024 sebesar 9,03 persen.", idx=0, title="Publikasi"):
    return Document(page_content=text, metadata={"faiss_id":idx, "document_title":title})


class InferenceFailureTests(unittest.TestCase):
    def transport(self, lines=(), status=200, error=""):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = status
        response.json.return_value = {"error":error}
        response.iter_lines.return_value = lines
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(response=response)
        session = MagicMock()
        session.post.return_value = response
        return response, session

    def assert_transport_error(self, expected, lines=(), status=200, error=""):
        response, session = self.transport(lines, status, error)
        with patch.object(generation, "_session", return_value=session):
            with self.assertRaises(InferenceError) as raised:
                list(generation.stream_generate("gemma2-base", []))
        self.assertEqual(raised.exception.code, expected)
        response.__exit__.assert_called_once()
        return raised.exception

    def test_http_500_memory_retains_reason_but_not_client_diagnostic(self):
        exc = self.assert_transport_error("model_memory", status=500,
                                         error="runner failed: unable to allocate memory secret/path")
        code, message = main.public_failure(exc)
        self.assertEqual(code,"model_memory")
        self.assertNotIn("secret",message)
        self.assertIn("Memori",message)

    def test_streamed_provider_error_is_not_generic_failure(self):
        self.assert_transport_error("model_memory", [b'{"error":"CUDA out of memory"}'])
        self.assert_transport_error("model_missing", status=404, error="model not found")
        self.assert_transport_error("model_busy", status=503, error="server busy")
        self.assert_transport_error("model_context", status=400, error="context length exceeded")

    def test_stream_protocol_corruption_and_incomplete_done(self):
        for wire in (b'null', b'[]', b'invalid', b'{"message":null}', b'{"message":{"content":123}}'):
            with self.subTest(wire=wire):
                self.assert_transport_error("model_invalid_response", [wire])
        self.assert_transport_error("model_stream_interrupted", [b'{"message":{"content":"partial"}}'])

    def test_timeout_wrapped_as_connection_error(self):
        response, session = self.transport()
        response.iter_lines.side_effect = requests.ConnectionError("Read timed out")
        with patch.object(generation, "_session", return_value=session):
            with self.assertRaises(InferenceError) as raised:
                list(generation.stream_generate("gemma2-base", []))
        self.assertEqual(raised.exception.code,"model_timeout")

    def test_prompt_batch_is_bounded_without_changing_context(self):
        from app.config import OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH
        payload = generation._payload("gemma2-base", [], 1, 0, 64, None, True)
        self.assertEqual(payload["options"]["num_ctx"], OLLAMA_NUM_CTX)
        self.assertEqual(payload["options"]["num_batch"], OLLAMA_NUM_BATCH)

    def test_cpu_override_is_explicit_and_default_keeps_auto(self):
        with patch.object(generation, "OLLAMA_NUM_GPU", 0):
            self.assertEqual(generation._payload("m", [], 1, 0, 64, None, True)["options"]["num_gpu"],0)
        with patch.object(generation, "OLLAMA_NUM_GPU", -1):
            self.assertNotIn("num_gpu",generation._payload("m", [], 1, 0, 64, None, True)["options"])

    def test_malformed_model_status_is_unavailable(self):
        for payload in (None, [], {"models":None}):
            response = MagicMock()
            response.__enter__.return_value = response
            response.json.return_value = payload
            session = MagicMock()
            session.get.return_value = response
            with patch.object(generation, "_session",return_value=session):
                self.assertFalse(generation.model_status()["reachable"])

    def test_failed_expansion_is_not_cached_and_retries_after_recovery(self):
        expansion._cache.clear()
        with patch.object(expansion,"generate",side_effect=[
                InferenceError("model_timeout","private"), "Kemiskinan penduduk Indonesia dan garis kemiskinan"]) as generate:
            with self.assertLogs("app.query_expansion_service",level="WARNING"):
                first=expansion.expand_query_result("kemiskinan Indonesia", CFG)
            second=expansion.expand_query_result("kemiskinan Indonesia", CFG)
            third=expansion.expand_query_result("kemiskinan Indonesia", CFG)
        self.assertFalse(first["cache_hit"])
        self.assertEqual(first["origin"],"terminology")
        self.assertNotIn("private",first["reason"])
        self.assertEqual(second["origin"],"model")
        self.assertTrue(third["cache_hit"])
        self.assertEqual(generate.call_count,2)


class AuditPipelineTests(unittest.TestCase):
    def run_case(self, ranked, answer="Data 9,03 persen [1].", use_rag=True):
        pipeline._rank_cache.clear()
        patches = [
            patch.object(pipeline,"expand_query_result",return_value={"queries":[],"raw":"","reason":None,"cache_hit":False}),
            patch.object(retrieval_service,"hybrid_search",return_value=[d for d,s in ranked]),
            patch.object(pipeline,"rerank",return_value=(ranked[:5],ranked)),
            patch.object(pipeline,"stream_generate",return_value=iter([{"text":answer}])),
        ]
        for p in patches:p.start()
        try:
            req=EvaluationRequest(question="kemiskinan Indonesia",use_rag=use_rag)
            return list(pipeline.run_pipeline(req,None,None,evaluation=True))
        finally:
            for p in reversed(patches):p.stop()

    def test_oversized_top_chunks_do_not_hide_later_fitting_evidence(self):
        ranked=[(document("X"*20000,i),10-i) for i in range(5)]+[(document(idx=5),2)]
        events=self.run_case(ranked)
        result=events[-1][1]
        self.assertEqual(len(result["sources"]),1)
        self.assertEqual(result["sources"][0]["source_id"],"faiss:5")
        self.assertEqual(result["sources"][0]["source_text"],result["contexts"][0])

    def test_no_context_capacity_is_not_claimed_as_no_evidence(self):
        with self.assertRaises(InferenceError) as raised:
            self.run_case([(document("X"*20000),3)])
        self.assertEqual(raised.exception.code,"context_unavailable")

    def test_empty_nonrag_is_a_failure_not_fake_excerpt_answer(self):
        with self.assertRaises(InferenceError) as raised:
            self.run_case([],answer="",use_rag=False)
        self.assertEqual(raised.exception.code,"model_empty_response")

    def test_grouped_citations_not_mistaken_for_data_numbers(self):
        docs=[document(),document(idx=1)]
        self.assertEqual(numbers("9,03 persen [1, 2]"),{"9,03"})
        self.assertEqual(check_answer("Data 9,03 persen [1, 2].",docs),[])
        self.assertTrue(check_answer("Data 9,03 persen [1, 8].",docs))

    def test_subgroup_number_does_not_silently_pass_as_general_population(self):
        docs=[document(title="Kemiskinan Anak Indonesia")]
        self.assertTrue(check_answer("Kemiskinan Indonesia 9,03 persen [1].",docs,question="kemiskinan Indonesia"))
        self.assertEqual(check_answer("Kemiskinan anak 9,03 persen [1].",docs,question="kemiskinan Indonesia"),[])
        self.assertEqual(check_answer("Angkanya 9,03 persen [1].",docs,question="kemiskinan anak"),[])

    def test_malformed_metadata_url_does_not_crash_rag(self):
        for url in ("http://[broken", "https:", "javascript:alert(1)", None):
            doc=document();doc.metadata["bps_url"]=url
            self.assertIsNone(retrieval_service.format_source(doc,3)["bps_url"])


class AuditApiTests(unittest.TestCase):
    def test_error_event_contains_safe_code_and_request_id(self):
        def failure(*args,**kwargs):
            yield "generating",{"label":"Menyusun jawaban"}
            raise InferenceError("model_memory","secret/path CUDA out of memory")
        runner=main.JobRunner(); client=TestClient(main.app)
        try:
            with patch.object(main,"jobs",runner),patch.dict(main._resources,ready=True),patch.object(main,"run_pipeline",side_effect=failure):
                with self.assertLogs("app.main",level="ERROR") as logs:
                    stream=client.post("/api/ask/stream",json={"question":"IPM"})
                    plain=client.post("/api/ask",json={"question":"IPM"})
                self.assertIn("stage=generating",str(logs.output))
                self.assertIn("model_memory",stream.text)
                self.assertIn("request_id",stream.text)
                self.assertNotIn("secret",stream.text)
                self.assertEqual(plain.status_code,503)
                self.assertEqual(plain.json()["detail"]["code"],"model_memory")
        finally:
            client.close();runner.close()

    def test_shutdown_cancels_running_jobs_and_rejects_new_admission(self):
        started,stopped=threading.Event(),threading.Event()
        def wait_for_cancel(*args,cancel,**kwargs):
            started.set()
            cancel.wait(2)
            stopped.set()
            if False:yield
        runner=main.JobRunner()
        try:
            with patch.object(main,"run_pipeline",side_effect=wait_for_cancel):
                events,cancel=runner.submit(AskRequest(question="IPM"))
                self.assertTrue(started.wait(1))
                runner.close()
                self.assertTrue(stopped.wait(1))
                self.assertTrue(cancel.is_set())
                with self.assertRaises(main.HTTPException) as raised:
                    runner.submit(AskRequest(question="IPM"))
                self.assertEqual(raised.exception.status_code,503)
        finally:
            runner.close()


class DevicePolicyTests(unittest.TestCase):
    def test_small_gpu_reserves_vram_but_explicit_settings_are_respected(self):
        from types import SimpleNamespace
        from app.device_policy import retrieval_device
        retrieval_device.cache_clear()
        try:
            with patch("app.device_policy.torch.cuda.is_available",return_value=True), patch("app.device_policy.torch.cuda.current_device",return_value=0), patch("app.device_policy.torch.cuda.get_device_properties",return_value=SimpleNamespace(total_memory=4*1024**3)):
                self.assertEqual(retrieval_device(""),"cpu")
                self.assertEqual(retrieval_device("cuda"),"cuda")
                self.assertEqual(retrieval_device("cpu"),"cpu")
        finally:
            retrieval_device.cache_clear()

    def test_large_gpu_uses_library_default(self):
        from types import SimpleNamespace
        from app.device_policy import retrieval_device
        retrieval_device.cache_clear()
        try:
            with patch("app.device_policy.torch.cuda.is_available",return_value=True), patch("app.device_policy.torch.cuda.current_device",return_value=0), patch("app.device_policy.torch.cuda.get_device_properties",return_value=SimpleNamespace(total_memory=12*1024**3)):
                self.assertIsNone(retrieval_device(""))
        finally:
            retrieval_device.cache_clear()

 
class AdditionalAuditTests(unittest.TestCase):
    def test_real_ipm_expansion_error_uses_canonical_fallback(self):
        with patch.object(expansion,"generate",return_value="Indikator Pembangunan Manusia (IPM)"):
            result=expansion.expand_query_result("Apa yang dimaksud dengan IPM?",CFG,use_cache=False)
        self.assertEqual(result["origin"],"terminology")
        self.assertIn("Indeks Pembangunan Manusia",result["queries"][0])

    def test_population_warning_is_not_hidden_by_target_warning(self):
        docs=[document("Target 2022 sebesar 6,50 persen.",title="Kemiskinan Anak Indonesia")]
        issues=check_answer("Kemiskinan Indonesia 2022 sebesar 6,50 persen [1].",docs,question="kemiskinan Indonesia")
        self.assertTrue(any("target" in issue for issue in issues))
        self.assertTrue(any("kelompok anak" in issue for issue in issues))

    def test_lifespan_can_restart_executor(self):
        def fake_pipeline(*args,**kwargs):
            yield "done",{"answer":"ok","answer_status":"basic_checks_passed","latency":{"first_token_s":None}}
        runner=main.JobRunner()
        with patch.object(main,"jobs",runner),patch.object(main,"build_indices",return_value=(None,None)),patch.object(main,"get_model"),patch.object(main,"run_pipeline",side_effect=fake_pipeline):
            for iteration in range(2):
                with TestClient(main.app) as client:
                    self.assertEqual(client.post("/api/ask",json={"question":"IPM"}).status_code,200)

    def test_queue_timeout_has_specific_code(self):
        with patch.object(main,"QUEUE_CONCURRENCY",1),patch.object(main,"MAX_QUEUE",1),patch.object(main,"QUEUE_WAIT_TIMEOUT",0):
            runner=main.JobRunner()
            runner.active.acquire()
            try:
                events,cancel=runner.submit(AskRequest(question="IPM"))
                self.assertEqual(events.get(timeout=2)[0],"queued")
                event,data=events.get(timeout=2)
                self.assertEqual(event,"error")
                self.assertEqual(data["code"],"queue_timeout")
            finally:
                runner.active.release()
                runner.close()
