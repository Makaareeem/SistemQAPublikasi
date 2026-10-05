# Perbaikan terarah: fungsi, latensi, dan integrasi

Tanggal: 2026-09-27.

## Yang diubah
- Threshold reranker benar-benar menyaring konteks; hasil UI dan pipeline konsisten.
- Metadata halaman chunk dan source_id unik digunakan tanpa menulis ulang korpus.
- Daftar isi tidak dipakai sebagai bukti, tokenisasi BM25 menangani kapitalisasi/tanda baca.
- Query embedding dibatch; ekspansi/pencarian berulang memiliki cache terbatas.
- Satu model UI tetap dipakai untuk ekspansi, jawaban, dan ringkasan.
- Token jawaban dikirim langsung sebelum ringkasan sumber; UI menandai draf.
- Panggilan tambahan tidak diperlukan jika tidak ada sumber yang lolos.
- Cuplikan asli terpisah dari ringkasan; isi bukti tidak dipotong menjadi 600 karakter.
- Non-RAG dipisahkan ke API evaluasi privat. Cache aplikasi dimatikan di endpoint evaluasi.
- Antrean terbatas, pembatalan, heartbeat, validasi input, health/readiness, render teks aman.
- Konfigurasi origin API terpisah, contoh reverse proxy, panduan menjalankan dan benchmark.

## Perubahan kontrak
- /api/ask dan /api/ask/stream menolak use_rag=false (422).
- /api/eval/ask menggantikan jalur non-RAG; opt-in dengan header kunci.
- top_k publik 1..5; kandidat retrieval tetap 20.
- sources berisi source_id, index, quote, citation_status; confidence heuristik dihapus.
- total_s mencakup queue_s; first_token_s diukur sejak permintaan masuk ke antrean backend.
- expanded event dikirim sebelum retrieval; sources dapat dikirim dua kali.
- Prompt generasi diubah agar ringkas, periode/jenis angka eksplisit; hasil eksperimen lama bukan baseline identik.
- Ekspansi angka/format bermasalah dilewati pada produksi; raw/note tetap tersedia untuk analisis.
- Awal startup lebih lama karena reranker dimuat sebelum readiness.

## Validasi yang tidak boleh disamakan
Tes unit/integrasi palsu membuktikan logika kode, bukan kualitas jawaban.
Angka percepatan, tingkat halusinasi, dan pencapaian TKT memerlukan uji nyata.
Tidak ada layanan publik atau tunnel yang dibuat.

## Rollback
Salinan file lama yang disentuh tersimpan pada .upgrade-backup/ dengan penanda waktu.
Jangan gunakan hasil benchmark/penelitian dari konfigurasi berbeda tanpa mencatat revisinya.

Dependensi: sentence-transformers 6.0.1 sebelumnya tidak cocok dengan Transformers 4.46.3;
diselaraskan ke 3.4.1. Versi dependensi langsung dikunci dan skor reranker dibuat eksplisit
sebagai logit mentah. Jangan menganggap threshold sudah terkalibrasi.
