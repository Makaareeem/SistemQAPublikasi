# Penyelesaian kalimat pada jawaban streaming

## Perilaku

Jawaban tetap dikirim bertahap melalui event token dan diperiksa pada event answer/done.
Batas model tidak dinaikkan: ringkas 150 token; detail mengikuti MAX_NEW_TOKENS
(default 384). Kebijakan ini hanya untuk jawaban, bukan query expansion.

app/answer_stream.py menerapkan batas lunak karakter: max(80, int(batas_token * 2.4)).
Dengan default, ringkas 360 karakter dan detail 921 karakter. Ini heuristik panjang
teks, bukan hitungan token model dan bukan jumlah paket streaming.

Setelah mendekati panjang tersebut, sistem berhenti pada akhir kalimat lengkap
berikutnya. Sitasi setelah titik, termasuk [1, 2] [3], ditunggu sebelum berhenti.
Titik desimal, pemisah ribuan, singkatan umum, elipsis, dan nomor daftar tidak
diperlakukan sebagai akhir kalimat. Aturan tanda baca bersifat konservatif dan
bukan analisis tata bahasa semantik lengkap.

Jika batas token model tercapai lebih dulu:
- Kalimat terakhir yang belum selesai dibuang dari jawaban akhir.
- Kalimat lengkap dan nomor sitasinya dipertahankan.
- Tidak menambah angka, isi kalimat, tanda titik, atau sitasi buatan.
- Bila belum ada satu kalimat lengkap pada RAG, tampilkan cuplikan literal berlabel
  dengan status needs_review; kartu sumber tetap tersedia.
- Evaluasi non-RAG tanpa kalimat lengkap mengembalikan model_incomplete_response.

Teks yang muncul selama streaming tetap provisional. Event answer/done mengganti
teks tersebut dengan hasil akhir yang telah dirapikan. Potongan terakhir masih
bisa terlihat sementara sebelum hasil akhir menggantikannya.

Baris sitasi mandiri yang hanya mengulang sitasi sebelumnya dihapus. Sitasi baru
tidak dihapus dan tidak dipindahkan ke klaim lain.

## Transport dan pembatalan

Generator HTTP model ditutup dalam finally: berlaku untuk penghentian dini,
pembatalan pengguna, error, dan penutupan iterator pipeline.
Menutup koneksi upstream tidak menjamin komputasi GPU berhenti seketika; layanan
inferensi menentukan respons terhadap disconnect.
Stream yang rusak tetap menjadi error, bukan dianggap jawaban selesai.

Pemeriksaan bukti dilakukan setelah perapian jawaban. API JSON dan SSE memakai
pipeline yang sama. Tidak ada perubahan arsitektur retrieval atau desain UI.

## Metrik

generation_metrics menambahkan:
- output_finish_reason: model_stop, sentence_boundary, token_limit_complete,
  token_limit_trimmed, atau token_limit_no_sentence.
- stopped_early, trimmed_incomplete_sentence, soft_character_limit.
- provider_metrics_available: apakah provider sempat mengirim metrik akhirnya.

done_reason, eval_count, dan durasi provider hanya dipertahankan bila benar-benar
diterima. Saat koneksi ditutup lebih awal, nilainya tidak direkayasa; perhitungan
throughput berbasis jumlah token harus menganggap metrik tersebut tidak tersedia.
Durasi generation_s dan total_s dari backend tetap diukur.
first_token_s tetap mengacu pada teks pertama yang diterima pipeline.

Kebijakan penyelesaian yang sama berlaku pada jawaban RAG dan evaluasi non-RAG;
catat perubahan ini jika membandingkan hasil eksperimen sebelum/sesudah perbaikan.

## Validasi

Regresi mencakup variasi pemotongan paket, desimal, ribuan, singkatan, nomor daftar
setelah judul, sitasi terpisah, limit tanpa kalimat, limit pada kalimat lengkap,
pembatalan, error stream, penutupan HTTP, kesamaan answer/done, dan metrik yang jujur.

Uji model nyata: gemma2-base di CPU, num_predict=64, berhenti dini pada sentence_boundary
dengan sitasi [1]. Waktu satu uji 17,316 detik; bukan benchmark atau evaluasi kualitas.
Data tersimpan di ../artifacts/code_audit/20260928/answer-completion.json.
Retrieval tidak dijalankan pada uji transport tersebut; sumber uji berupa contoh buatan.

Perbaikan fungsional tambahan: publikasi tanpa URL tetap bisa muncul sebagai sumber
lain jika judul/tahunnya berbeda. Ketiadaan URL tidak lagi menyamakan semuanya.

Masalah akurasi faktual dan kegagalan GPU dari audit sebelumnya masih terpisah.
Perbaikan akhir kalimat tidak membuktikan bahwa angka atau interpretasi model benar.
