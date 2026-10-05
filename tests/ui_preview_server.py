"""Loopback-only UI fixture. Synthetic responses; never used by the production API.
Run: python -B tests/ui_preview_server.py
Test questions: 'server sibuk', 'jawaban gagal', 'tunggu jawaban'.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import time

WEB = Path(__file__).resolve().parents[1] / "web"
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)
    def log_message(self, *_):
        pass
    def do_GET(self):
        if self.path == "/api/health":
            self.send_json(200, dict(ready=True, inference_reachable=True,
                available_models=["llama3.2-finetuned", "llama3.2-base", "gemma2-finetuned", "gemma2-base"],
                default_model="gemma2-base"))
        else:
            super().do_GET()
    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def emit(self, event, data):
        self.wfile.write(("event: " + event + "\ndata: " + json.dumps(data) + "\n\n").encode())
        self.wfile.flush()
    def do_POST(self):
        if self.path != "/api/ask/stream":
            self.send_json(404, {}); return
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        q = data["question"]
        if "sibuk" in q:
            self.send_json(429, {}); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache"); self.end_headers()
        try:
            self.emit("queued", {"label": "Menunggu giliran pemrosesan..."})
            if "tunggu" in q:
                for _ in range(20):
                    time.sleep(1); self.emit("heartbeat", {})
            time.sleep(.4); self.emit("expanding", {"label": "Memperluas pertanyaan..."})
            process = dict(original_query=q, expanded_queries=["dimensi Indeks Pembangunan Manusia umur panjang dan hidup sehat pengetahuan standar hidup layak"],
                expansion_note="Contoh data untuk pengujian tampilan.", candidates_before_rerank=20, rerank_threshold=-1,
                reranked=[dict(document_title="Contoh Publikasi Pembangunan Manusia 2024", selected=True, passed=True, score=5.82)])
            time.sleep(.6); self.emit("expanded", {"label": "Perluasan selesai; pertanyaan asli tetap digunakan.", "process": process})
            source = dict(index=1, document_title="Contoh Publikasi Pembangunan Manusia 2024", bps_url="https://www.bps.go.id/",
                page_start=24, page_end=25, document_year=2024, score=5.82,
                quote="IPM dibangun dari tiga dimensi dasar: umur panjang dan hidup sehat, pengetahuan, serta standar hidup layak.",
                source_text="DATA SIMULASI UI. IPM dibangun dari tiga dimensi dasar: umur panjang dan hidup sehat, pengetahuan, serta standar hidup layak. Teks tambahan ini hanya untuk menguji panel cuplikan.")
            sources = [source, dict(source, index=2, document_title="Contoh Indikator Kesejahteraan Rakyat 2024", score=4.29, page_start=51, page_end=51)]
            self.emit("sources", {"sources": sources})
            self.emit("generating", {"label": "Menyusun jawaban..."})
            if "gagal" in q:
                self.emit("error", {"code": "model_unavailable", "request_id": "a"*32}); return
            answer = "Contoh jawaban untuk pengujian tampilan.\n\nIndeks Pembangunan Manusia memiliki tiga dimensi: umur panjang dan hidup sehat, pengetahuan, serta standar hidup layak. [1, 2]\n\nGunakan cuplikan dan tautan publikasi untuk memeriksa konteks penjelasan."
            for word in answer.split(" "):
                self.emit("token", {"text": word + " "}); time.sleep(.07)
            self.emit("answer", {"answer": answer, "warnings": []})
            self.emit("done", dict(answer=answer, sources=sources, process=process, warnings=[],
                other_sources=[dict(source, document_title="Contoh Statistik Kesejahteraan Rakyat 2025")],
                latency=dict(total_s=5.6, queue_s=0, expansion_s=.6, search_rerank_s=.8, generation_s=4.2),
                config=dict(model_key=data["model_key"]), request_id="a"*32))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("UI fixture: http://127.0.0.1:8765 (synthetic data, no model calls)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
