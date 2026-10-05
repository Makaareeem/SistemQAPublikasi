"""Sentence stopping must be independent of chunk boundaries and preserve evidence."""
import json
import threading
import unittest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document
from app.answer_stream import AnswerStream, sentence_ends, remove_duplicate_citation_lines
from app import pipeline, generation_service as generation
from app.schemas import AskRequest, EvaluationRequest
from app.inference_errors import InferenceError


class SentenceBoundaryTests(unittest.TestCase):
    def test_decimal_thousands_abbreviation_and_citation(self):
        text = "Menurut Dr. Ali, Kab. X memiliki 1.234,56 penduduk per km2 [1]. Angka 9.03 persen [2]."
        ends = sentence_ends(text, final=True)
        self.assertEqual(len(ends), 2)
        self.assertTrue(text[:ends[0]].endswith("[1]."))
        self.assertEqual(ends[-1], len(text))

    def test_numbered_list_and_ellipsis_are_not_finished_sentences(self):
        self.assertEqual(sentence_ends("1. IPM belum..."), [])
        self.assertEqual(sentence_ends("Nilai 9.", final=False), [])
        self.assertEqual(sentence_ends("Nilai 9.03", final=True), [])

    def test_list_marker_after_heading_is_not_a_complete_sentence(self):
        text="Berikut beberapa indikator yang dijelaskan:\n\n1. Penjelasan belum lengkap"
        self.assertEqual(sentence_ends(text,final=True),[])
        output=AnswerStream(384);output.push(text)
        self.assertEqual(output.finish("length")[0],"")

    def test_citation_after_period_waits_for_all_split_groups(self):
        text = "Satu kalimat cukup panjang untuk menjelaskan indikator dan konteks dengan tepat sekali."
        output = AnswerStream(1)
        for part in (text, " [", "1", ", ", "2", "]", " [", "3", "]"):
            output.push(part)
            self.assertFalse(output.stopped)
        output.push(" Kalimat berikut")
        self.assertTrue(output.stopped)
        self.assertEqual(output.text, text+" [1, 2] [3]")

    def test_fragmentation_does_not_change_early_stop(self):
        wire = ("Indikator ini dijelaskan dengan konteks wilayah dan periode data yang cukup lengkap [1]. "
                "Kalimat ini tidak perlu dilanjutkan karena jawaban sudah cukup.")
        values = []
        for size in (1, 2, 7, 37, len(wire)):
            output = AnswerStream(1)
            rendered = []
            for offset in range(0, len(wire), size):
                rendered.append(output.push(wire[offset:offset+size]))
                if output.stopped: break
            final, meta = output.finish()
            self.assertTrue(meta["stopped_early"])
            self.assertEqual("".join(rendered).strip(), final)
            values.append(final)
        self.assertEqual(len(set(values)), 1)

    def test_hard_limit_removes_only_unfinished_tail(self):
        output=AnswerStream(384)
        output.push("Angka 9,03 persen [1]. Kalimat kedua belum sele")
        answer,meta=output.finish("length")
        self.assertEqual(answer,"Angka 9,03 persen [1].")
        self.assertEqual(meta["output_finish_reason"],"token_limit_trimmed")

    def test_hard_limit_keeps_citations_after_period(self):
        output=AnswerStream(384)
        output.push("Angka 9,03 persen. [1, 2] [3] Kalimat belum sele")
        answer,meta=output.finish("length")
        self.assertEqual(answer,"Angka 9,03 persen. [1, 2] [3]")

    def test_hard_limit_complete_sentence_is_not_truncated(self):
        output=AnswerStream(384)
        output.push("Angka 9,03 persen [1].")
        answer,meta=output.finish("length")
        self.assertEqual(answer,"Angka 9,03 persen [1].")
        self.assertFalse(meta["trimmed_incomplete_sentence"])
        self.assertEqual(meta["output_finish_reason"],"token_limit_complete")

    def test_hard_limit_without_complete_sentence_returns_no_fabricated_period(self):
        output=AnswerStream(384)
        output.push("Pada tahun 2024 jumlahnya adalah 9,")
        answer,meta=output.finish("length")
        self.assertEqual(answer,"")
        self.assertEqual(meta["output_finish_reason"],"token_limit_no_sentence")

    def test_natural_stop_does_not_discard_unpunctuated_model_answer(self):
        output=AnswerStream(384);output.push("Indeks Pembangunan Manusia [1]")
        self.assertEqual(output.finish("stop")[0],"Indeks Pembangunan Manusia [1]")

    def test_incomplete_reference_does_not_invent_source_id(self):
        output=AnswerStream(384);output.push("Angka 9,03 persen. [1")
        answer,meta=output.finish("length")
        self.assertEqual(answer,"Angka 9,03 persen.")
        self.assertNotIn("[1]",answer)

    def test_duplicate_standalone_citation_removed_but_new_citation_retained(self):
        self.assertEqual(remove_duplicate_citation_lines("Data [1].\n\n[1]\n"),"Data [1].")
        self.assertEqual(remove_duplicate_citation_lines("Data.\n[1]"),"Data.\n[1]")


class PipelineStreamTests(unittest.TestCase):
    def setUp(self):
        self.doc=Document(page_content="Angka 9,03 persen merupakan data kemiskinan Indonesia tahun 2024.",
                          metadata={"faiss_id":1,"document_title":"Statistik Indonesia","document_year":"2024"})
        pipeline._rank_cache.clear()
        self.patches=[
            patch.object(pipeline,"expand_query_result",return_value={"queries":[],"raw":"","reason":None,"cache_hit":False}),
            patch.object(pipeline.retrieval,"hybrid_search",return_value=[self.doc]),
            patch.object(pipeline,"rerank",return_value=([(self.doc,4)],[(self.doc,4)])),
        ]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def run_stream(self, parts, req=None, cancel=None):
        with patch.object(pipeline,"stream_generate",return_value=parts):
            return list(pipeline.run_pipeline(req or AskRequest(question="kemiskinan Indonesia"),None,None,cancel=cancel))

    def test_truncated_answer_is_same_in_answer_and_done_and_metrics_honest(self):
        events=self.run_stream(iter([
            {"text":"Angka 9,03 persen [1]. Kalimat belum selesai"},
            {"metrics":{"done_reason":"length","eval_count":384}}]))
        final=events[-1][1]
        intermediate=next(d for stage,d in events if stage=="answer")
        self.assertEqual(final["answer"],"Angka 9,03 persen [1].")
        self.assertEqual(intermediate["answer"],final["answer"])
        self.assertEqual(final["generation_metrics"]["eval_count"],384)
        self.assertEqual(final["generation_metrics"]["done_reason"],"length")
        self.assertTrue(final["generation_metrics"]["provider_metrics_available"])

    def test_early_stop_closes_transport_and_never_reads_the_remainder(self):
        closed=threading.Event()
        sentence="Angka 9,03 persen berasal dari data kemiskinan Indonesia yang disajikan untuk tahun 2024 [1]."
        def model_stream():
            try:
                yield {"text":sentence+" Kalimat selanjutnya"}
                self.fail("The rest of generation must not be consumed")
            finally:closed.set()
        with patch.object(pipeline,"AnswerStream",side_effect=lambda _:AnswerStream(1)):
            events=self.run_stream(model_stream())
        result=events[-1][1]
        self.assertTrue(closed.is_set())
        self.assertEqual(result["answer"],sentence)
        self.assertEqual(result["generation_metrics"]["output_finish_reason"],"sentence_boundary")
        self.assertFalse(result["generation_metrics"]["provider_metrics_available"])
        self.assertNotIn("eval_count",result["generation_metrics"])
        self.assertEqual("".join(d["text"] for s,d in events if s=="token").strip(),result["answer"])

    def test_cancellation_closes_upstream_without_done(self):
        cancel,closed=threading.Event(),threading.Event()
        def model_stream():
            try:
                yield {"text":"Awal kalimat"}
                cancel.set()
                yield {"text":"lanjutan"}
            finally:closed.set()
        with self.assertRaises(InterruptedError):
            self.run_stream(model_stream(),cancel=cancel)
        self.assertTrue(closed.is_set())

    def test_broken_stream_is_not_changed_into_success(self):
        def broken():
            yield {"text":"Kalimat lengkap [1]."}
            raise InferenceError("model_stream_interrupted")
        with self.assertRaises(InferenceError):
            self.run_stream(broken())

    def test_empty_after_length_limit_rag_shows_labeled_literal_excerpt(self):
        events=self.run_stream(iter([{"text":"Angka 9,"},{"metrics":{"done_reason":"length"}}]))
        result=events[-1][1]
        self.assertEqual(result["answer_status"],"needs_review")
        self.assertTrue(result["answer"].startswith("Bagian sumber"))
        self.assertIn(self.doc.page_content,result["answer"])

    def test_incomplete_nonrag_returns_error_not_a_fabricated_answer(self):
        with self.assertRaises(InferenceError) as error:
            self.run_stream(iter([{"text":"Jawabannya 9,"},{"metrics":{"done_reason":"length"}}]),
                            EvaluationRequest(question="kemiskinan",use_rag=False))
        self.assertEqual(error.exception.code,"model_incomplete_response")

    def test_sources_without_urls_keep_distinct_publications(self):
        second=Document(page_content="Data lain.",metadata={"faiss_id":2,"document_title":"Publikasi Lain","document_year":"2024"})
        with patch.object(pipeline,"rerank",return_value=([(self.doc,4)],[(self.doc,4),(second,3)])):
            result=self.run_stream(iter([{"text":"Angka 9,03 persen [1]."}]),
                                   AskRequest(question="kemiskinan",top_k=1))[-1][1]
        self.assertEqual(len(result["other_sources"]),1)
        self.assertEqual(result["other_sources"][0]["document_title"],"Publikasi Lain")

    def test_closing_real_transport_generator_exits_http_response(self):
        response=MagicMock();response.__enter__.return_value=response
        response.iter_lines.return_value=[b'{"message":{"content":"Awal."}}',b'{"done":true}']
        session=MagicMock();session.post.return_value=response
        with patch.object(generation,"_session",return_value=session):
            iterator=generation.stream_generate("mock",[])
            self.assertEqual(next(iterator)["text"],"Awal.")
            iterator.close()
        response.__exit__.assert_called_once()
