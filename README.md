# Question Answering Publikasi Statistik BPS

Web dengan backend RAG lokal (FastAPI + Ollama + FAISS/BM25 + reranker).
API pengguna selalu memakai RAG. API penelitian terpisah dan nonaktif secara default.
Perubahan ini menyiapkan integrasi/deploy, bukan bukti bahwa akurasi atau tingkat TKT tertentu sudah tercapai.

## Menjalankan lokal

1. Aktifkan environment Python yang berisi dependensi proyek, misalnya `conda activate rag-sistem`.
   Instal dependensi bila diperlukan: `python -m pip install -r requirements.txt`.
   Untuk tes: `python -m pip install -r requirements-dev.txt`. Versi langsung dikunci;
   pilih build PyTorch CPU/CUDA sesuai perangkat sebelum instalasi.
2. Jika belum memiliki konfigurasi, salin `.env.example` ke `.env`; jangan menimpa token yang sudah ada.
3. Jalankan Ollama dan pastikan model di `app/config.py` tersedia.
   Registrasi model bila perlu: `python -m deploy.setup_ollama`.
4. Jalankan `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`.
5. Buka http://127.0.0.1:8000. Dokumentasi API lokal: http://127.0.0.1:8000/docs.

`run.ps1` memakai Python environment aktif. Untuk interpreter spesifik:
`$env:QA_PYTHON = "D:/Laptop/Anaconda/envs/rag-sistem/python.exe"`, lalu `.\run.ps1 -m uvicorn app.main:app`.
Gunakan `--reload` hanya untuk pengembangan. Satu worker diperlukan agar antrean dan cache berada dalam satu proses.
Jangan memperbesar concurrency sebelum mengukur VRAM dan latensi.

## Arsitektur dan batas tanggung jawab

Browser → API FastAPI → pipeline RAG → Ollama lokal.
FAISS/BM25, embedding, reranker, token HF, dan model tidak dikirim ke browser.

- `web/index.html`: tampilan, `web/app.js`: rendering aman dan pembaca SSE.
- `web/api-config.js`: alamat API publik saja; tidak boleh menyimpan rahasia.
- `app/main.py`: HTTP, validasi, antrean terbatas, SSE, health/readiness, otorisasi evaluasi.
- `app/schemas.py`: kontrak input; API publik tidak menerima non-RAG.
- `app/pipeline.py`: alur yang sama untuk JSON/SSE, waktu per tahap, pembatalan, hasil penelitian.
- Service retrieval/reranker/expansion/generation: logika tiap tahap.
- `app/evidence.py`: pemeriksaan dasar angka/sitasi dan cuplikan asli; bukan validator kebenaran semantik.
- `app/cache.py`: cache memori terbatas dengan TTL; tidak dipakai oleh endpoint evaluasi.

Alur pengguna:
1. Satu ekspansi oleh model pilihan UI; query asli selalu dipertahankan.
2. Ekspansi yang mengubah angka/periode atau berubah menjadi jawaban dilewati dan alasannya ditampilkan.
3. Embedding query dalam satu batch, dense + BM25, RRF, rerank maksimal 20 kandidat.
4. Threshold diterapkan sungguhan. Maksimal 5 chunk lolos dan sesuai anggaran konteks.
5. Tanpa bukti: respons langsung tanpa panggilan LLM jawaban/sitasi.
6. Jawaban ditampilkan bertahap sebagai sementara; setelah selesai, angka dan nomor sitasi diperiksa.
7. Jawaban tetap ditampilkan; temuan pemeriksaan dasar menjadi catatan sumber (needs_review).
8. Kartu sumber hanya menampilkan cuplikan asli; tidak ada generasi ringkasan per sumber.

Teks jawaban dan sitasi menggunakan chunk penuh yang sama. Anggaran konservatif berbasis byte UTF-8
memilih chunk utuh, tidak memangkas kalimat di tengah. Kadang jumlah sumber kurang dari lima; panel
proses menjelaskan seleksinya. Tahun terbit bukan tahun data. `source_id` berbasis FAISS unik pada
snapshot KB, sedangkan `chunk_id` lama dipertahankan untuk pelacakan. Identitas lintas snapshot perlu
dipasangkan dengan `kb_fingerprint`.

## Endpoint

| Endpoint | Kegunaan |
| --- | --- |
| GET /api/health | Keterjangkauan Ollama, model yang benar-benar terdaftar, kesiapan indeks |
| GET /api/ready | HTTP 503 sampai backend dan model default siap |
| POST /api/ask | Jawaban JSON; RAG wajib |
| POST /api/ask/stream | Alur yang sama dengan SSE untuk web |
| POST /api/eval/ask | Penelitian privat; default HTTP 404 |

Input publik:
`{"question":"Apa yang dimaksud TPAK?","model_key":"llama3.2-finetuned","use_rag":true,"top_k":5,"response_style":"detail"}`

SSE: queued, expanding, expanded, retrieving, reranked, sources, generating, token, answer, done. Heartbeat dapat muncul sepanjang antrean/pemrosesan. Error memiliki request_id.
Token adalah draf; hanya event answer/done merupakan jawaban setelah pemeriksaan.
API JSON mengembalikan bentuk hasil akhir yang sama, tanpa token antara.

Respons: answer, answer_status, sources, other_sources, warnings, latency, config, process, cache,
generation_metrics, request_id. Skor reranker adalah kecocokan pencarian, bukan confidence kebenaran.
Nomor [n] mengacu pada sources[index=n]. Cuplikan bukan selalu bukti bahwa pertanyaan sudah terjawab.

Khusus eksperimen melalui API evaluasi privat: aktifkan ENABLE_EVALUATION_API=true dan set EVALUATION_API_KEY acak minimal
32 karakter. Kirim header X-Evaluation-Key. Hanya endpoint ini menerima use_rag=false.
Cache aplikasi otomatis dilewati dan contexts berisi teks persis yang dikirim ke model.
Cache internal Ollama/model yang sudah hangat tetap ada: laporkan cold/warm secara terpisah.
strict_expansion=false tersedia untuk eksperimen perilaku ekspansi mentah; nilai default true.
Jangan membandingkan hasil sebelum/sesudah perubahan prompt tanpa mencatat versi konfigurasi.

## Kecepatan dan cara mengukur

- Connection reuse ke Ollama; keep_alive default 15m mengurangi kemungkinan reload model.
- Embedding query asli + ekspansi dibatch; query identik tidak dicari dua kali.
- Cache ekspansi dan pencarian/reranking terbatas, TTL 600 detik; model ekspansi termasuk dalam key.
- Reranker dimuat saat startup, bukan pada pertanyaan pertama.
- Sumber ditampilkan sebelum jawaban; token jawaban dikirim bertahap.
- Maksimal dua panggilan LLM pada alur normal: ekspansi dan jawaban utama.
  Cache ekspansi menghindari panggilan pertama untuk pertanyaan/model berulang.
- citation_s tetap tersedia dengan nilai 0 untuk kompatibilitas notebook; sources[].answer
  berupa string kosong dan citation_status bernilai excerpt_only. Tidak ada ringkasan sumber.
- Output detail dibatasi 384 token; gunakan mode Ringkas untuk jawaban lebih pendek.
- Tidak menjalankan model lokal paralel secara agresif agar tidak berebut VRAM.

`python tools/benchmark_api.py --repeat 3`
Jalankan hanya setelah backend aktif. Output JSON mencatat client wall time, queue, expansion,
search_rerank, generation, citation, first_token, cache, dan durasi/token asli dari Ollama.
Run pertama belum tentu cold start. Bandingkan pertanyaan, model, konfigurasi, dan perangkat yang sama.
Waktu backend total mencakup antrean, tetapi tidak seluruh waktu jaringan browser.
Untuk sampling GPU/RAM dan benchmark terperinci, gunakan notebook pengujian di bawah.
Sampling GPU NVIDIA memerlukan paket opsional nvidia-ml-py; hasil aktual belum diukur.

## Deployment dengan backend lokal

Pilihan paling sederhana: frontend dan API satu origin HTTPS, melalui reverse proxy ke FastAPI lokal.
Template tersedia di `deploy/Caddyfile.example`. Ganti domain contoh, siapkan DNS/TLS, lalu uji SSE.
Backend/Ollama tetap berada di komputer/server lokal yang hidup dan terjangkau oleh proxy.

Frontend statis boleh ditempatkan terpisah:
- Atur window.API_BASE melalui web/api-config.js ke origin HTTPS API yang benar.
- ALLOWED_ORIGINS backend harus berisi origin frontend yang tepat.
- localhost pada browser pengunjung adalah komputer pengunjung, bukan backend Anda.
- Backend lokal perlu koneksi privat/tunnel/proxy yang dikelola untuk menjangkau origin API.
- Jangan membuka port Ollama 11434 ke internet. Jangan menanam API key rahasia dalam JavaScript.
- Blokir /api/eval/* pada jalur publik; contoh proxy sudah melakukannya.
- Untuk layanan institusi, gunakan akses jaringan/SSO serta pembatasan trafik di gateway.
  Antrean aplikasi terbatas mencegah pekerjaan tak terbatas, tetapi bukan pengganti rate limit gateway.

Tidak ada domain/tunnel/hosting yang otomatis dipublikasikan oleh perubahan ini.

## Pemeriksaan

`python -B -m unittest discover -s tests -p "test_*.py" -v`
`node tests/frontend.test.cjs`
Tes memakai inferensi palsu: memeriksa integrasi/kontrak dan regresi, bukan kualitas model.
`python smoke_test.py` memerlukan backend aktif dan menjalankan satu pertanyaan nyata.

Keterbatasan yang masih perlu bukti operasional:
- threshold -1 masih heuristik dan perlu kalibrasi;
- pemeriksaan angka/sitasi tidak membuktikan seluruh makna, wilayah, atau periode sudah benar;
- prompt dan ekspansi masih perlu evaluasi berpasangan base/finetuned;
- uji beban, kualitas jawaban, akurasi per skenario, aksesibilitas/browser, serta deployment HTTPS nyata;
- anggaran konteks konservatif dapat mengurangi recall konteks; pantau warnings dan jumlah sumber.

Excel TKT dipakai sebagai acuan bukti integrasi, dokumentasi, dan pengujian lingkungan operasional.
Tidak ada nilai atau tingkat TKT yang dinyatakan tercapai hanya dari perubahan kode.

Referensi implementasi:
- https://docs.ollama.com/api/chat (stream, keep_alive, metrik)
- https://docs.ollama.com/capabilities/structured-outputs (schema JSON)
- https://fastapi.tiangolo.com/advanced/events/ (lifespan)

Dependensi diperbaiki: sentence-transformers 3.4.1 sesuai Transformers 4.46.3.
Reranker memakai skor logit mentah (Identity); threshold -1 mengacu pada skala ini,
bukan probabilitas sigmoid. Ini perlu dicatat saat membandingkan eksperimen lama.

## Notebook pengujian performa

Notebook nb23 dikelola terpisah di proyek penelitian SkripsiNabil, setelah dipindahkan pengguna.
Folder Sistem QA RAG tidak lagi menyimpan salinan notebook tersebut.
Panduan: [Pengujian performa](docs/PENGUJIAN-PERFORMA.md).

requirements-notebook.txt tetap diperlukan karena nb23 membacanya dari folder sistem ini.
Notebook mengakses API backend untuk mengukur retrieval, generasi, respons keseluruhan, dan memori.
Pengujian sistem memakai RAG aktif melalui /api/ask; API evaluasi privat tidak diperlukan
untuk benchmark produksi. Lokasi hasil dan flag pengujian mengikuti konfigurasi nb23.

## Pembatalan dan catatan jawaban

Pembatalan menutup POST/stream browser. Backend memeriksa sinyal batal selama ekspansi dan jawaban, serta di antara tahap retrieval. Koneksi Ollama ditutup saat pembatalan terdeteksi.
Operasi CPU/GPU yang sudah berjalan dan koneksi yang sedang menunggu data tidak selalu berhenti seketika;
panggilan jaringan tetap dibatasi timeout. GET status layanan berjalan terpisah dari pertanyaan.
Status needs_review berarti jawaban ditampilkan dengan catatan, bukan telah terbukti benar.
Cuplikan asli dipilih berdasarkan kecocokan pertanyaan beserta kalimat di sekitarnya.

## Validasi pertanyaan sebelum pencarian

API JSON, streaming, dan evaluasi memeriksa pertanyaan sebelum masuk antrean,
ekspansi, atau retrieval. Input kosong, terlalu panjang, karakter kontrol,
angka/tanda baca saja, sapaan, percobaan tanpa topik (cek/tes), dan pola acak
yang jelas mendapat HTTP 422 dengan kode serta arahan yang aman ditampilkan.
Web menampilkan bubble peringatan dan mempertahankan pertanyaan serta hasil sebelumnya.

Aturan bersama berada di web/question-rules.json; backend tetap memvalidasi bila
aturan web belum termuat. Istilah singkat (IPM, TPT, P0), nama wilayah, serta
pertanyaan definisi tetap diterima. Tidak ada batas minimal huruf yang memblokir
semua singkatan dan tidak ada kewajiban menyebut wilayah/tahun.
Validasi ini konservatif: bukan pengklasifikasi lengkap topik BPS atau penjamin
bahwa pertanyaan dapat dijawab. Input yang belum dikenali tetap melalui pipeline
RAG dan pemeriksaan bukti. Threshold reranker serta arsitektur retrieval tidak berubah.
Kasus bersama di tests/question_validation_cases.json menguji kesetaraan API/web.

## Audit kode dan diagnosis model 28 September 2026

Laporan terbaru: [AUDIT-2026-09-28.md](docs/AUDIT-2026-09-28.md).
Laporan ini membedakan pengujian simulasi, inference nyata, dan masalah kualitas yang belum selesai.
Kasus gemma2-base direproduksi sebagai kegagalan alokasi CUDA; jangan menganggap model
tersedia di daftar model berarti selalu mampu menghasilkan jawaban.

OLLAMA_NUM_BATCH=128 membatasi batch prompt; OLLAMA_NUM_CTX tetap 8192.
OLLAMA_NUM_GPU=-1 mempertahankan pemilihan perangkat Ollama; OLLAMA_NUM_GPU=0
memaksa CPU untuk host yang gagal mengalokasikan GPU. Pilihan CPU sudah diuji,
namun lebih lambat dan tidak otomatis memperbaiki isi jawaban. Tidak ada pergantian
CPU otomatis atau retry tersembunyi yang diaktifkan.

Embedding/reranker memakai CPU bila instalasi Torch tidak mendukung CUDA.
Pada GPU <=6 GiB, default retrieval juga CPU; pengaturan perangkat eksplisit tetap dihormati.
Kebijakan ini bukan jaminan memori cukup. Host yang diuji memakai Torch CPU sejak awal.

Pengujian regresi:
python -B -m unittest discover -s tests -p "test_*.py"
node tests/frontend.test.cjs
node tests/frontend-audit.test.cjs

## Jawaban selesai pada akhir kalimat

Jawaban tetap streaming, dengan penghentian pada kalimat lengkap mendekati batas
panjang dan perlindungan sitasi. Jika model mencapai batas token di tengah kalimat,
hasil akhir membuang bagian yang belum selesai. Tidak ada panggilan model tambahan
untuk menyambung kalimat. Lihat [perilaku dan metrik](docs/ANSWER-COMPLETION.md).
