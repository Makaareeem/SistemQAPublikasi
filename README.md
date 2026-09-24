# Sistem RAG Publikasi BPS

## Struktur

```
app/
  config.py                 konfigurasi terpusat (env var, model registry, prompt, threshold, queue)
  retrieval_service.py      dense (FAISS+Nomic) + BM25 + Reciprocal Rank Fusion
  reranker_service.py       cross-encoder rerank (madebyaris/rerank-indonesia) + filter threshold
  query_expansion_service.py  perluas 1 pertanyaan jadi kalimat pencarian tambahan
  citation_service.py       jawaban singkat per-sumber (format JSON via Ollama)
  prompt_constructor.py     penyusunan prompt RAG, identik dengan template fine-tuning
  generation_service.py     pemanggilan Ollama via HTTP, termasuk health check & JSON mode
  main.py                   endpoint FastAPI (/api/ask, /api/ask/stream, /api/health), CORS,
                             antrian request (semaphore), static web
web/
  index.html                UI: landing animasi, live progress (SSE), kartu sitasi, navbar info
deploy/
  setup_ollama.py           generate Modelfile dari config.py, download GGUF, ollama create
tests/                      black-box testing (belum diisi)
```

## Setup

1. Conda env `rag-sistem` (Python 3.11) — lihat `run.ps1`. Install dependency:
   ```
   .\run.ps1 -m pip install -r requirements.txt
   ```
2. Copy `.env.example` menjadi `.env`, isi `HF_Faiss` dengan token HuggingFace Hub.
3. Pastikan Ollama sudah terinstal dan aktif (`ollama list` tidak error).
4. Registrasi keempat model (kalau belum ada di `ollama list`):
   ```
   .\run.ps1 -m deploy.setup_ollama
   ```
   Mengunduh GGUF dari HF Hub, menulis `Modelfile` dinamis dari `SYSTEM_PROMPT`/`MODEL_REGISTRY`, `ollama create` tiap model. Jalankan ulang kalau `SYSTEM_PROMPT` berubah.

## Verifikasi cepat (opsional, sebelum coba web UI)

```
.\run.ps1 smoke_test.py
```

Cek koneksi Ollama, hybrid search + rerank, dan generation dalam satu jalan tanpa browser.

## Menjalankan

Dari folder root:

```
.\run.ps1 -m uvicorn app.main:app --reload
```

Buka `http://localhost:8000` untuk web UI. Startup pertama kali bisa lama (download FAISS index dari HF Hub ke `app/kb_cache/`, load model embedding & reranker).

### Endpoint API

- `GET /api/health` — status Ollama, daftar model tersedia
- `POST /api/ask` — respons JSON biasa (sekali balas), untuk client terprogram/notebook evaluasi:
  `{"question": "...", "model_key": "llama3.2-finetuned", "use_rag": true, "top_k": 5}`
- `POST /api/ask/stream` — sama seperti di atas tapi respons SSE (Server-Sent Events), tiap tahap
  pipeline (expanding/retrieving/reranking/citing/generating/queued/done) dikirim begitu selesai.
  Dipakai web UI untuk panel proses live.

Response `/api/ask` berisi `answer`, `sources` (tiap sumber ada `score` hasil reranker + `answer`
sitasi singkat), `latency` (retrieval/citation/generation/total — relevan untuk Efficiency
Evaluation), `config`, dan `process` (query hasil expansion, kandidat sebelum rerank, semua skor
kandidat + status lolos/ditolak threshold — untuk debug kualitas retrieval).

### Alur pipeline (kalau `use_rag=true`)

```
Query → Query Expansion (model = model_key yang dipilih)
      → Dense(FAISS) + BM25, dari query asli + hasil expansion → RRF fusion
      → Cross-Encoder Rerank → filter RERANK_SCORE_THRESHOLD → top-k
      → Citation per-sumber (JSON) + Generate jawaban (keduanya model = model_key yang dipilih)
```

### Antrian request

`QUEUE_CONCURRENCY` (default `1`) di `config.py` membatasi berapa pertanyaan yang diproses
bersamaan — penting karena satu laptop menahan 4 model GGUF + FAISS + reranker sekaligus di
memori. Permintaan berikutnya menunggu (dapat notifikasi "menunggu giliran" di UI), bukan
langsung dieksekusi paralel dan berebut resource. Naikkan via env var kalau pindah ke server
dengan resource lebih besar.

## Status

- [x] retrieval_service.py — hybrid dense+BM25, RRF fusion
- [x] reranker_service.py — cross-encoder rerank + threshold filter
- [x] query_expansion_service.py — perluasan query
- [x] citation_service.py — sitasi per-sumber (JSON)
- [x] prompt_constructor.py — template identik fine-tuning, prompt bersih tanpa RAG
- [x] generation_service.py — HTTP ke Ollama + health check + JSON mode
- [x] main.py — CORS, static files, validasi, SSE streaming, antrian
- [x] web/index.html — landing animasi, live progress, kartu sitasi, navbar info
- [x] deploy/setup_ollama.py — generate Modelfile dinamis, download GGUF, registrasi Ollama
- [x] smoke_test.py — verifikasi cepat hybrid search + rerank + generation
- [ ] black-box tests
- [ ] kalibrasi k/threshold berbasis data (masih nilai heuristik)
- [ ] notebook evaluasi Tujuan 3 (RAGAS, ablasi, 5 skenario) — belum dimulai
