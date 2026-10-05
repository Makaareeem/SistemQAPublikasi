# Pengujian performa yang terhubung ke backend

Notebook nb23 telah dipindahkan pengguna ke proyek penelitian SkripsiNabil.
Notebook dan hasil pengujiannya dikelola di sana; folder sistem ini menyediakan API dan dependensi.

Dari folder Sistem QA RAG, jalankan backend dan Ollama seperti pada README.
Notebook mengakses backend melalui http://127.0.0.1:8000 jika berada di komputer yang sama.
requirements-notebook.txt tetap disimpan di sini karena dirujuk oleh sel instalasi nb23.

Pengujian utama memakai RAG aktif melalui /api/ask, mencatat waktu retrieval, generasi jawaban,
respons keseluruhan, serta penggunaan memori. Pengujian streaming dan generator terpisah bersifat opsional.
Pengaturan pertanyaan, jumlah ulangan, flag, dan lokasi hasil mengikuti notebook aktif.
Hasil utama notebook berupa system_performance_all.csv per sesi.
RAM proses Ollama belum mencakup RAM khusus backend; GPU/RAM sistem mengukur seluruh perangkat.

API /api/eval/ask disediakan terpisah untuk eksperimen penelitian yang memerlukan konteks asli
atau non-RAG. Endpoint tersebut tidak perlu diaktifkan untuk pengujian performa produksi.
Cache/model internal Ollama tetap dapat hangat; laporkan status cache dan kondisi pengujian.

## Pembaruan cuplikan saja

Generasi ringkasan per sumber sudah dihapus. Alur normal kini hanya menjalankan model untuk
ekspansi dan jawaban utama. citation_s tetap 0 agar notebook kompatibel; sumber memakai
quote asli, answer kosong, dan citation_status=excerpt_only.
Bagian perbandingan berikut mencatat versi sebelumnya, bukan spesifikasi tahap terbaru.

## Perbedaan perubahan sistem sebelumnya

Perbandingan mengacu pada salinan sebelum pembaruan di .upgrade-backup/20260927-203006.

| Bagian | Sebelumnya | Saat ini | Dampak |
| --- | --- | --- | --- |
| Penyajian jawaban | Ringkasan sumber dahulu, jawaban menunggu generasi selesai | Token jawaban lebih dahulu, ringkasan menyusul | Jawaban mulai terlihat lebih cepat; total belum tentu turun sebanyak itu |
| Permintaan berulang | Tahap ekspansi/pencarian diulang | Cache terbatas untuk ekspansi, embedding, dan hasil rerank | Mempercepat pertanyaan yang berulang; evaluasi melewati cache |
| Persiapan model | Reranker dimuat saat dipakai | Dimuat saat startup; keep_alive Ollama 15m eksplisit dan koneksi dipakai ulang | Mengurangi beban awal permintaan, memindahkan sebagian waktu ke startup |
| Embedding | Pemanggilan query terpisah | Query asli dan ekspansi dibatch, duplikat dihapus | Mengurangi pekerjaan berulang |
| Batas jawaban detail | 512 token | Default 384 token | Dapat mempercepat sekaligus memendekkan jawaban |
| Ekspansi | Prompt lama, temperature 0.3 | Prompt baru, temperature 0, validasi lebih ketat | Mengubah hasil pencarian; bukan optimasi kecepatan saja |
| Bukti dan sitasi | Pemeriksaan lebih longgar | Pemeriksaan angka/sitasi/cuplikannya, fallback ke cuplikan asli | Dapat menolak jawaban atau mengosongkan ringkasan sumber |
| Pemilihan konteks | Alur lama | Threshold efektif, chunk utuh dengan batas konteks | Dapat mengubah sumber yang dipilih |

Bobot GGUF tidak dilatih ulang oleh pembaruan ini. Query asli tetap dicari bersama
maksimal satu ekspansi yang diterima; jika ekspansi ditolak, pencarian memakai query asli.
Untuk pertanyaan baru dengan bukti cukup, umumnya tetap tiga panggilan LLM:
ekspansi, jawaban, dan ringkasan sumber.

Integrasi notebook pada giliran ini tidak mengubah prompt, ekspansi, threshold, model,
UI, atau pipeline. Besar peningkatan kecepatan dan kualitas masih harus diukur memakai model nyata.
