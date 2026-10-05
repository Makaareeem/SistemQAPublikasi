import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("demo_launch", Path(__file__).parent / "runtime" / "launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)

class RuntimeTests(unittest.TestCase):
    def test_defaults_keep_ollama_private_and_eval_disabled(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.dict(os.environ, {"QA_DATA_DIR": directory}, clear=True):
            launch.configure()
            self.assertEqual(os.environ["OLLAMA_HOST"], "127.0.0.1:11434")
            self.assertEqual(os.environ["ENABLE_EVALUATION_API"], "false")
            self.assertEqual(os.environ["QUEUE_CONCURRENCY"], "1")
            self.assertTrue((Path(directory) / "ollama").is_dir())

    def test_requires_persistent_storage(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.dict(os.environ, {"QA_DATA_DIR": directory + "/missing"}, clear=True):
            with self.assertRaises(RuntimeError):
                launch.configure()

    def test_missing_default_or_duplicate_models_rejected(self):
        registry = {"one": {}, "two": {}}
        for values in ["two", "one,one", "one,unknown", ""]:
            with patch.dict(os.environ, {"DEFAULT_MODEL_KEY": "one", "DEMO_MODELS": values}, clear=True):
                with self.assertRaises(ValueError):
                    launch.selected_models(registry)

    def test_model_order_preserved(self):
        with patch.dict(os.environ, {"DEFAULT_MODEL_KEY": "one", "DEMO_MODELS": "two,one"}, clear=True):
            self.assertEqual(launch.selected_models({"one": {}, "two": {}}), ["two", "one"])

if __name__ == "__main__":
    unittest.main()
