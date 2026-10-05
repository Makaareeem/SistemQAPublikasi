# Catatan validasi 2026-09-27

- Tes backend memakai model, retrieval, dan HTTP transport simulasi.
- Browser diuji melalui server simulasi terpisah di loopback, bukan server Ollama.
- Tampilan jawaban akhir, ekspansi, panel proses, sumber, cuplikan asli, dan pembatalan diverifikasi.
- Teks markup pada ekspansi/judul tampil sebagai teks literal.
- Pembaca SSE diuji dengan CRLF, UTF-8 terfragmentasi, heartbeat komentar, EOF, dan koneksi putus.
- API publik menolak non-RAG. API evaluasi memerlukan aktivasi dan kunci.
- Pemeriksaan dependensi setelah penyesuaian: tidak ada requirement yang rusak.
- Runtime setempat: Python environment rag-sistem, Torch 2.5.1, Transformers 4.46.3,
  sentence-transformers 3.4.1, huggingface-hub 0.36.2, Pillow 12.3.0.
- Belum dilakukan: inference model nyata, pengukuran kecepatan cold/warm perangkat,
  uji akurasi BPS per skenario, uji beban operasional, serta publikasi HTTPS.
- Angka waktu dalam preview browser adalah data simulasi dan bukan hasil benchmark.

Jalankan ulang:
python -B -m unittest discover -s tests -p "test_*.py" -v
node tests/frontend.test.cjs
python -m pip check

Untuk pengukuran asli setelah backend aktif:
python tools/benchmark_api.py --repeat 3

## Integrasi notebook performa

- Salinan notebook pengguna terhubung ke endpoint produksi/evaluasi/streaming yang ada.
- 32 tes unittest lulus: 24 tes sistem dan 8 tes notebook; semuanya tanpa inferensi nyata.
- Semua 9 sel kode notebook berhasil dikompilasi; output dan execution_count dikosongkan.
- Hash file asli Downloads sama dengan hash saat integrasi; file asli tidak diubah.
- Tes baru memeriksa pemilihan endpoint/header evaluasi, penolakan non-RAG publik,
  kewajiban contexts/cache evaluasi, SSE Unicode/multiline, waktu token/jawaban/done,
  abstention tanpa token, error server, dan stream yang terputus.
- Dependensi notebook tambahan dicatat di requirements-notebook.txt.
  Pada pemeriksaan ini pandas dan psutil belum tersedia dalam environment rag-sistem.
- Sel hardware, benchmark model, dan agregasi pandas belum dijalankan pada perangkat nyata.
  Tidak ada angka peningkatan kecepatan atau kualitas yang diklaim dari tes simulasi.
- Integrasi ini tidak mengubah kode app/, web/, prompt, atau parameter inferensi.
