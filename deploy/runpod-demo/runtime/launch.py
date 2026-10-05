"""Runpod adapter. The copied QA application is imported without source changes."""
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

LOG = logging.getLogger("qa.runpod")
STATE = {"status": "initializing"}
ROOT = Path(__file__).resolve().parents[1]

def configure():
    volume = Path(os.environ.get("QA_DATA_DIR", "/runpod-volume"))
    if not volume.is_dir():
        raise RuntimeError("Attach a persistent volume at QA_DATA_DIR before starting.")
    for folder in ("ollama", "hf", "registrations"):
        (volume / folder).mkdir(exist_ok=True)
    os.environ.update({
        "INFERENCE_URL": "http://127.0.0.1:11434",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(volume / "ollama"),
        "HF_HOME": str(volume / "hf"),
        "KB_CACHE_DIR": str(ROOT / "app" / "kb_cache"),
        "ENABLE_EVALUATION_API": "false",
        "QUEUE_CONCURRENCY": "1",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_NO_CLOUD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for name, value in {
        "DEFAULT_MODEL_KEY": "llama3.2-finetuned", "MAX_QUEUE": "2",
        "QUEUE_WAIT_TIMEOUT": "60", "OLLAMA_TIMEOUT": "120",
        "EMBEDDING_DEVICE": "cpu", "RERANKER_DEVICE": "cpu",
        "OMP_NUM_THREADS": "4", "TOKENIZERS_PARALLELISM": "false",
    }.items():
        os.environ.setdefault(name, value)
    return volume

def get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/ping":
            self.send_error(404)
            return
        self.send_response({"initializing": 204, "ready": 200, "failed": 503}[STATE["status"]])
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
    def log_message(self, *args):
        pass

def selected_models(registry):
    keys = [k.strip() for k in os.getenv("DEMO_MODELS", ",".join(registry)).split(",") if k.strip()]
    if not keys or len(keys) != len(set(keys)) or any(k not in registry for k in keys):
        raise ValueError("DEMO_MODELS must contain unique registered model keys.")
    if os.environ["DEFAULT_MODEL_KEY"] not in keys:
        raise ValueError("The default model must be included in DEMO_MODELS.")
    return keys

def register_models(volume, process):
    from app.config import MODEL_REGISTRY
    from deploy.setup_ollama import build_modelfile_content
    manifest = json.loads((ROOT / "snapshot-manifest.json").read_text(encoding="utf-8"))
    available = {m["name"].removesuffix(":latest") for m in get_json("http://127.0.0.1:11434/api/tags")["models"]}
    for key in selected_models(MODEL_REGISTRY):
        if process.poll() is not None:
            raise RuntimeError("Ollama stopped while preparing models.")
        cfg = MODEL_REGISTRY[key]
        relative = "assets/gguf/" + key + "/" + cfg["gguf_filename"]
        gguf = ROOT / relative
        if not gguf.is_file():
            raise RuntimeError("Missing copied GGUF for " + key)
        content = build_modelfile_content(str(gguf), cfg["system_role"], cfg["repeat_penalty"])
        fingerprint = hashlib.sha256((manifest["files"][relative]["sha256"] + content).encode()).hexdigest()
        marker = volume / "registrations" / (key + ".sha256")
        if cfg["ollama_name"] in available and marker.is_file() and marker.read_text() == fingerprint:
            continue
        LOG.info("Registering copied model %s", key)
        modelfile = volume / "registrations" / (key + ".Modelfile")
        modelfile.write_text(content, encoding="utf-8")
        subprocess.run(["ollama", "create", cfg["ollama_name"], "-f", str(modelfile)], check=True, timeout=900)
        marker.write_text(fingerprint, encoding="utf-8")

def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    health = ollama = backend = None
    def shutdown(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, shutdown)
    try:
        port = int(os.getenv("PORT", "8000"))
        health_port = int(os.getenv("PORT_HEALTH", "8081"))
        if port == health_port:
            raise ValueError("PORT and PORT_HEALTH must be different.")
        health = http.server.ThreadingHTTPServer(("0.0.0.0", health_port), HealthHandler)
        threading.Thread(target=health.serve_forever, daemon=True).start()
        volume = configure()
        os.chdir(ROOT)
        ollama = subprocess.Popen(["ollama", "serve"])
        deadline = time.monotonic() + 60
        while True:
            try:
                get_json("http://127.0.0.1:11434/api/tags")
                break
            except Exception:
                if ollama.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Ollama did not start.")
                time.sleep(1)
        register_models(volume, ollama)
        backend = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
            "--port", str(port), "--workers", "1", "--no-access-log",
        ])
        deadline = time.monotonic() + int(os.getenv("QA_STARTUP_TIMEOUT", "1200"))
        while backend.poll() is None and ollama.poll() is None:
            try:
                get_json("http://127.0.0.1:" + str(port) + "/api/ready")
                STATE["status"] = "ready"
            except Exception:
                if STATE["status"] == "ready" or time.monotonic() >= deadline:
                    raise RuntimeError("QA backend failed readiness.")
            time.sleep(2)
        raise RuntimeError("A required service stopped.")
    except KeyboardInterrupt:
        LOG.info("Stopping demo services.")
    except Exception:
        STATE["status"] = "failed"
        LOG.exception("Demo worker failed")
        return 1
    finally:
        STATE["status"] = "failed"
        stop(backend)
        stop(ollama)
        if health:
            health.shutdown()
            health.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
