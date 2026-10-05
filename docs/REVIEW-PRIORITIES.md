Catatan historis: lihat [audit terbaru](AUDIT-2026-09-28.md) untuk perbaikan yang sudah diterapkan dan temuan tersisa.

# Temuan lanjutan setelah penghapusan ringkasan sumber

Perubahan tahap ini hanya menghapus generasi ringkasan sumber dan tampilan terkait.
Arsitektur hybrid retrieval, RRF, reranking, query expansion, serta jawaban utama tetap sama.
citation_s=0 dan sources[].answer kosong dipertahankan untuk klien/notebook yang sudah ada.

## Prioritas perbaikan berikutnya (belum diterapkan)

1. Kesesuaian bukti: pemeriksaan angka memeriksa keberadaan teks angka, belum memastikan
   keterkaitan indikator, wilayah, periode data, satuan, atau populasi. Angka target/realisasi
   yang kebetulan sama tetap dapat lolos. Referensi: app/evidence.py check_answer.
2. Jawaban versus cuplikan: model membaca chunk penuh, sedangkan kartu menunjukkan potongan
   pilihan berbasis kata. Klaim jawaban dapat berasal dari bagian lain yang belum terlihat.
   Pilihan perbaikan: tampilkan bagian yang mendukung klaim dan akses teks chunk lengkap.
   Referensi: app/prompt_constructor.py build_user_content dan app/evidence.py source_excerpt.
3. Sitasi per klaim: referensi dikelompokkan seperti [1, 2] belum dipahami; kecocokan angka belum
   membuktikan dukungan makna. Kalimat nonnumerik tanpa sitasi juga belum diperiksa per klaim.
   Pertahankan jawaban dengan catatan; jangan kembali menutup seluruh jawaban otomatis.
4. Perluasan: angka baru diperiksa, tetapi perubahan wilayah/indikator secara semantik belum.
   Cadangan istilah masih kamus terbatas. Ukur manfaat retrieval dari asli versus asli+ekspansi.
   Referensi: app/query_expansion_service.py validate_expansion.
5. Pemilihan sumber: top-k berbasis chunk, bukan publikasi unik; beberapa kartu dapat berasal
   dari buku yang sama. Kelompokkan tampilan per publikasi dengan halaman terpisah tanpa
   membuang bukti. Threshold saat ini belum dikalibrasi pada pertanyaan dalam/luar cakupan.
6. Anggaran konteks: hitungan byte UTF-8 konservatif dapat membuang chunk yang sebenarnya
   masih muat. Perlu pengukuran sesuai tokenizer model sebelum mengubah pemilihan sumber.
7. Pembatalan: sinyal diperiksa setelah data stream diterima. Saat menunggu data pertama atau
   operasi CPU/GPU aktif, penghentian tidak selalu segera. Perlu uji cancel selama prefill,
   retrieval, antrean, dan timeout. Jangan mengklaim GPU langsung berhenti.
8. Observabilitas: memori backend belum diukur khusus. Error harus tetap ramah pengguna,
   sementara log internal menyimpan jenis error dan request_id untuk diagnosis.

Urutan yang disarankan: kecocokan bukti dan sitasi -> keselarasan cuplikan -> ekspansi dan
keberagaman sumber -> pengujian pembatalan. Temuan ini adalah audit kode, bukan hasil
evaluasi akurasi seluruh korpus.

Cuplikan asli memastikan teks berasal dari dokumen, bukan memastikan dokumen tersebut
menjawab pertanyaan atau bahwa interpretasi model benar.
