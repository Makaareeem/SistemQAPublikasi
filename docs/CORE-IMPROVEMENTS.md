# Perbaikan inti 28 September 2026

Arsitektur tetap: query asli + maksimal satu perluasan, hybrid dense/BM25, RRF, reranker,
jawaban streaming dan sumber. Model UI tetap digunakan untuk seluruh tahap model.
Jumlah kandidat, threshold, dan konfigurasi hosting tidak diubah.

- Ekspansi membersihkan penomoran/pembuka, menerima sinonim yang tidak menyalin tahun
  lalu menyertakan pertanyaan asli untuk mempertahankan angka. Bila model gagal atau mengulang
  pertanyaan, kamus istilah statistik terbatas menjadi cadangan yang ditandai transparan.
  Topik tanpa istilah yang dikenal tetap dapat memakai query asli saja.
- Jawaban tidak diganti pesan tidak terverifikasi. Catatan pemeriksaan dipertahankan,
  status needs_review tidak berarti jawaban benar. Jawaban tanpa bukti tetap abstention.
- Cuplikan literal dipilih di sekitar kalimat yang cocok dengan pertanyaan; tidak dibatasi
  ke kata pertama atau diberi tanda titik buatan. Cuplikan langsung terlihat, ringkasan
  kontekstual dapat dibuka jika tersedia. Sitasi bernomor pada jawaban dapat diklik.
- Bubble memisahkan antrean penuh, model tidak tersedia, timeout, input salah, dan pembatalan.
  Detail exception/path/traceback tidak dirender pada UI; log teknis tetap tersedia di server.
- POST streaming browser dibatalkan dengan AbortController. Backend memeriksa cancellation
  selama ekspansi/jawaban/sitasi dan di antara tahap pencarian. GET health adalah request
  terpisah. Pembatalan tidak menjamin operasi GPU/CPU atau socket yang sedang menunggu
  berhenti seketika; slot dilepas setelah worker keluar dan transport ditutup.

Validasi: 33 tes backend dan tes frontend lulus; rendering DOM diuji dengan simulasi.
Uji model llama3.2-finetuned memakai contoh sumber sintetis, bukan angka hasil penelitian.
Perluasan TPT menguraikan istilah dengan benar. Ringkasan sumber dapat tetap fallback ke
cuplikan asli. Evaluasi kualitas menyeluruh dan pemeriksaan visual browser belum dilakukan.

Restart backend dan refresh browser setelah perubahan. Backup versi sebelumnya ada di
.upgrade-backup/core-* dan .upgrade-backup/ui-*. File di luar Sistem QA RAG tidak diubah.
