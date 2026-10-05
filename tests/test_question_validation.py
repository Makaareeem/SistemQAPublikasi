"""Input checks must prevent model work without rejecting useful short questions."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import main
from app.question_validation import question_issue, MESSAGES

CASES = json.loads((Path(__file__).parent / "question_validation_cases.json").read_text(encoding="utf-8"))


class QuestionValidationTests(unittest.TestCase):
    def test_shared_browser_api_cases(self):
        for question, expected in CASES:
            with self.subTest(question=question):
                self.assertEqual(question_issue(question), expected)

    def test_invalid_input_never_enters_queue_even_when_backend_not_ready(self):
        with TestClientWithoutStartup() as client, patch.object(main.jobs, "submit") as submit, patch.dict(main._resources, ready=False):
            for endpoint in ("/api/ask", "/api/ask/stream"):
                for question, expected in CASES:
                    if expected is None:
                        continue
                    with self.subTest(endpoint=endpoint, question=question):
                        response = client.post(endpoint, json={"question": question})
                        self.assertEqual(response.status_code, 422)
                        body = response.json()
                        detail = body["detail"] if isinstance(body["detail"], dict) else body
                        self.assertEqual(detail["code"], expected)
                        self.assertEqual(detail["detail"], MESSAGES[expected])
                        self.assertNotIn("sources", body)
            submit.assert_not_called()

    def test_valid_short_topics_reach_readiness_check(self):
        client = TestClient(main.app)
        try:
            with patch.dict(main._resources, ready=False):
                for question in ("IPM", "TPT", "P0", "kemiskinan", "Halo, cek IPM Jawa Tengah 2024"):
                    self.assertEqual(client.post("/api/ask", json={"question": question}).status_code, 503)
        finally:
            client.close()

    def test_private_evaluation_keeps_auth_before_semantic_validation(self):
        client = TestClient(main.app)
        try:
            with patch.object(main, "ENABLE_EVALUATION_API", True), patch.object(main, "EVALUATION_API_KEY", "a"*32), patch.object(main.jobs, "submit") as submit:
                self.assertEqual(client.post("/api/eval/ask", json={"question":"cek"}).status_code,401)
                response = client.post("/api/eval/ask", json={"question":"cek"}, headers={"X-Evaluation-Key":"a"*32})
                self.assertEqual(response.status_code,422)
                submit.assert_not_called()
        finally:
            client.close()


class TestClientWithoutStartup:
    """Do not load real indices or GPU models for API contract tests."""
    def __enter__(self):
        self.client = TestClient(main.app)
        return self.client

    def __exit__(self, *args):
        self.client.close()
