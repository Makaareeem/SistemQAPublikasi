"""Core behavior regression: no live model or downloads."""
import threading
import unittest
from unittest.mock import patch, MagicMock
import requests
from langchain_core.documents import Document
from app import query_expansion_service as expansion, generation_service as generation
from app.config import MODEL_REGISTRY, DEFAULT_MODEL_KEY
from app.evidence import source_excerpt
from app.main import public_failure

CFG = MODEL_REGISTRY[DEFAULT_MODEL_KEY]

class AnswerExperienceTests(unittest.TestCase):
    def test_numbered_expansion_is_cleaned_and_missing_year_preserved(self):
        with patch.object(expansion, "generate", return_value="1. Tingkat Pengangguran Terbuka TPT Jawa Tengah"):
            result=expansion.expand_query_result("TPT Jawa Tengah 2024?", CFG, use_cache=False)
        self.assertEqual(len(result["queries"]),1)
        self.assertIn("2024",result["queries"][0])
        self.assertIn("Tingkat Pengangguran Terbuka",result["queries"][0])
        self.assertEqual(result["origin"],"model")

    def test_repeated_question_gets_transparent_terminology_fallback(self):
        q="kemiskinan Jawa Tengah 2024?"
        with patch.object(expansion, "generate", return_value=q):
            result=expansion.expand_query_result(q,CFG,use_cache=False)
        self.assertEqual(result["origin"],"terminology")
        self.assertIn("persentase penduduk miskin",result["queries"][0])
        self.assertIn("Jawa Tengah 2024",result["queries"][0])

    def test_invented_number_not_used(self):
        with patch.object(expansion,"generate",return_value="Kemiskinan 2024 sebesar 99 persen"):
            result=expansion.expand_query_result("kemiskinan 2024",CFG,use_cache=False)
        self.assertNotIn("99",result["queries"][0])

    def test_unknown_topic_does_not_get_fabricated_expansion(self):
        with patch.object(expansion,"generate",return_value="xyz"):
            result=expansion.expand_query_result("xyz",CFG,use_cache=False)
        self.assertEqual(result["queries"],[])
        self.assertEqual(result["origin"],"original")

    def test_excerpt_is_literal_with_context_not_first_words(self):
        text="Pengantar publikasi. "*100+"Target kemiskinan 2024 ditetapkan. Realisasi kemiskinan 2024 sebesar 9,03 persen. Angka ini lebih rendah dari sebelumnya."
        quote=source_excerpt("realisasi kemiskinan 2024",text)
        self.assertIn(quote,text)
        self.assertIn("9,03",quote)
        self.assertIn("Target",quote)
        self.assertFalse(quote.startswith("Pengantar"))

    def test_long_excerpt_does_not_invent_a_period(self):
        text="Kemiskinan "+("data "*400)
        quote=source_excerpt("kemiskinan",text)
        self.assertIn(quote,text)
        self.assertFalse(quote.endswith("."))

    def test_cancel_before_all_model_stages_sends_no_request(self):
        cancel=threading.Event();cancel.set()
        with patch.object(generation,"_session") as session:
            with self.assertRaises(InterruptedError): generation.generate("mock",[],cancel=cancel)
            session.assert_not_called()
        with patch.object(expansion,"generate") as generate:
            with self.assertRaises(InterruptedError): expansion.expand_query_result("Q",CFG,cancel=cancel)
            generate.assert_not_called()

    def test_cancelling_stream_closes_transport(self):
        cancel=threading.Event()
        response=MagicMock();response.__enter__.return_value=response
        def lines(**kw):
            yield b'{"message":{"content":"awal"}}'
            cancel.set()
            yield b'{"message":{"content":"lanjut"}}'
        response.iter_lines.side_effect=lines
        session=MagicMock();session.post.return_value=response
        with patch.object(generation,"_session",return_value=session):
            iterator=generation.stream_generate("mock",[],cancel=cancel)
            self.assertEqual(next(iterator)["text"],"awal")
            with self.assertRaises(InterruptedError): next(iterator)
        response.__exit__.assert_called_once()

    def test_public_error_never_returns_exception_text(self):
        for error in (ValueError("secret/path/traceback"),requests.Timeout("secret"),requests.ConnectionError("secret")):
            code,message=public_failure(error)
            self.assertNotIn("secret",message)
            self.assertNotIn("traceback",message)
            self.assertTrue(code)
