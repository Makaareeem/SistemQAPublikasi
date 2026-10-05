# Salinan demo QA BPS untuk Runpod Serverless

Status: paket persiapan lokal. Belum dibangun menjadi image Linux, belum diunggah,
dan belum diuji dengan GPU/endpoint Runpod. Tidak ada URL demo aktif dari paket ini.

## Yang dipertahankan

- Aplikasi lokal, .env, model lokal, notebook, dan .upgrade-backup tetap di tempatnya.
- snapshot/ berisi salinan nyata kode app/, web/, dependensi, indeks FAISS,
  metadata, dan empat GGUF. Tidak memakai symlink/hardlink ke aplikasi lokal.
- snapshot/snapshot-manifest.json mencatat SHA-256 dan asal setiap salinan.
- Perubahan deployment hanya berada di folder ini. Tidak ada perubahan prompt,
  retrieval, reranker, validasi sumber, maupun parameter konteks/anggaran jawaban.
- Model embedding/reranker diunduh pertama kali ke volume Runpod; bukan salinan cache
  laptop. Pin EMBEDDING_REVISION/RERANKER_REVISION jika ingin mereplikasi versinya persis.
- ENV cloud terpisah dari .env laptop. Kunci evaluasi laptop tidak disalin.
- Daftar empat model dipertahankan, tetapi hanya satu model generasi dimuat bersamaan.

## Susunan demo

Browser -> Cloudflare Worker (tampilan + gerbang aman)
        -> Runpod Serverless Load Balancer (FastAPI + pipeline + Ollama)
        -> Network Volume (registrasi Ollama dan cache embedding/reranker).

Mengapa ada gerbang web? Endpoint Serverless Runpod memerlukan API key.
Kunci tersebut tidak boleh ditanam di JavaScript atau dibagikan melalui URL.
Worker menyimpannya sebagai Secret. Frontend tetap desain yang sama, tanpa React
atau penulisan ulang UI. Salinan web asli juga tetap ada di image Runpod.

Ini berarti dua layanan untuk URL demo yang bisa dibagikan: Cloudflare untuk akses
web ringan, Runpod untuk seluruh proses QA. Mengakses halaman tidak membangunkan GPU.
GPU baru dipanggil setelah pengguna menekan Tanyakan.

Login demo memakai HTTP Basic lewat HTTPS. Gunakan kata sandi demo ASCII acak
minimal 12 karakter. Kata sandi ini boleh diberikan kepada penguji; API key Runpod
tidak boleh. Ini pembatasan demo, bukan implementasi akun pengguna/SSO production.

## 1. Periksa salinan

Dari folder ini, jalankan:
    python -B create_snapshot.py --verify

Perintah membandingkan SHA-256 snapshot dengan sumber lokal. Jika sumber lokal
kemudian diedit, perbedaan akan dilaporkan; salinan tidak disinkronkan otomatis.
Exporter menolak menimpa snapshot yang sudah ada.

## 2. Akun dan alat yang diperlukan

- Akun Runpod dengan metode pembayaran/saldo, dibuat dan dikelola sendiri.
- Akun registry Docker privat (Docker Hub/GHCR) untuk image berisi model dan data.
- Docker dengan dukungan build Linux amd64. Belum tersedia pada sesi persiapan ini.
- Akun Cloudflare untuk Workers; bisa mulai dengan alamat workers.dev.
- Node.js/npm untuk menerbitkan gerbang.
- Pastikan hak distribusi model/data sesuai. Jangan menerbitkan image/model ke
  registry publik secara tidak sengaja.

Jangan mengirim password/token akun di chat. Jangan memasukkan token sebagai build
argument Docker atau menyimpan .env laptop di registry.

## 3. Bangun image dan uji Linux

Buka terminal di folder paket ini. Ganti REGISTRY_USER dengan akunmu:
    docker build --platform linux/amd64 -t REGISTRY_USER/qa-bps-demo:v1 .
    docker login
    docker push REGISTRY_USER/qa-bps-demo:v1

Dockerfile memakai image resmi Ollama. Tag latest hanya bootstrap untuk build
pertama; catat versi dan pin ke digest yang berhasil diuji sebelum final demo.
Base image menyediakan Python sistem (dapat berbeda dari Python 3.11 laptop).
Build harus lulus pip check; kompatibilitas Linux belum dibuktikan sebelum build.

Image berukuran beberapa GB karena berisi GGUF asli. Jangan menilai cold start dari
upload/deployment pertama: penarikan image dan cache awal dapat jauh lebih lama.
Jangan memakai konteks build folder proyek utama; gunakan folder paket ini saja.

Untuk uji lokal container (hanya bila Docker/GPU tersedia), gunakan port berbeda
agar tidak mengganggu backend lokal:
    docker volume create qa-bps-runpod-demo
    docker run --rm --gpus all -p 18000:8000 -p 18081:8081 -v qa-bps-runpod-demo:/runpod-volume REGISTRY_USER/qa-bps-demo:v1

Jangan menjalankan bersamaan dengan inferensi lokal jika VRAM laptop tidak cukup.
Untuk uji CPU, hilangkan --gpus all dan tambahkan -e OLLAMA_NUM_GPU=0.
Jangan menjalankan inferensi demo pada container sebelum readiness berhasil.

## 4. Siapkan penyimpanan dan cache Runpod

Buat Network Volume, mulai sekitar 30 GB (cek ruang aktual setelah inisialisasi).
Pilih lokasi yang memiliki GPU yang akan dipakai. Volume membatasi lokasi worker.

Disarankan untuk inisialisasi pertama: jalankan Pod sementara dengan image yang
sama dan volume tersebut. Volume Pod biasanya di /workspace: set QA_DATA_DIR=/workspace.
Biarkan entrypoint image berjalan sampai log menunjukkan aplikasi siap. Verifikasi
/api/ready lewat HTTP port 8000. Langkah ini mengisi registrasi model dan cache
retrieval sebelum scale-to-zero diuji, sehingga startup Serverless tidak bergantung
pada unduhan awal yang panjang. Volume harus sama dengan yang dipasang ke endpoint.

Pod sementara juga menagih biaya selama berjalan. Setelah cache siap, hentikan
penggunaan Pod sesuai petunjuk Runpod dan pertahankan Network Volume.
Jangan menghapus volume atau menjalankan Pod dan Serverless menulis cache bersamaan.

## 5. Buat endpoint Serverless

Di Runpod: Serverless -> New Endpoint -> Import from Docker Registry.
Gunakan image privat v1 dan kredensial registry melalui pengaturan resmi Runpod.

Pengaturan awal:
- Endpoint Type: Load Balancer, bukan Queue.
- Active/min workers: 0 (tidur saat tidak dipakai).
- Max workers: 1 (antrean aplikasi saat ini berada dalam satu proses).
- GPU: kelas 16 GB yang tersedia; pastikan worker punya RAM host cukup (target 16 GB).
- Network Volume: volume yang sudah diisi.
- Expose HTTP ports: 8000 dan 8081. Jangan buka 11434.
- PORT=8000; PORT_HEALTH=8081; HEALTH_CHECK_PATH=/ping.
- QA_DATA_DIR=/runpod-volume.
- Salin pengaturan nonrahasia dari runpod.env.example.
- Idle timeout: mulai 60 detik; semakin panjang semakin sedikit reload, tetapi
  waktu idle yang masih aktif tetap menagih.
- FlashBoot: aktifkan jika tersedia.

Jangan menaikkan jumlah worker untuk demo ini tanpa merancang koordinasi antrean.
HTTP /ping di port 8081 mengembalikan 204 saat inisialisasi, 200 ketika aplikasi
dan model default siap, 503 jika gagal. API utama pada port 8000.
Endpoint /api/eval/ask dinonaktifkan pada salinan cloud.

Catat URL base endpoint yang diberikan Runpod. Jangan memakai URL /run atau /runsync.
Buat API key dengan hak invoke yang dibatasi hanya ke endpoint demo jika tersedia.

## 6. Terbitkan tampilan/gerbang aman

Masuk ke subfolder gateway. Edit RUNPOD_ORIGIN di wrangler.jsonc dengan URL
https://ENDPOINT_ID.api.runpod.ai yang diberikan Runpod (tanpa path tambahan).

    npm install
    npx wrangler login
    npx wrangler secret put RUNPOD_API_KEY
    npx wrangler secret put DEMO_PASSWORD
    npx wrangler deploy

Input secret dilakukan pada prompt tersembunyi/terminal, bukan dimasukkan ke JS.
Catat package-lock.json hasil instalasi untuk build berikutnya. Jangan menambahkan
registry/model/key backend ke public/. Frontend menggunakan /api pada origin yang sama.
Gunakan URL workers.dev hasil deploy sebagai alamat demo dan username demo.
Domain pribadi belum diperlukan. Batas/biaya Workers mengikuti paket Cloudflare.

## 7. Uji sebelum membagikan alamat

- Buka URL dari perangkat lain dengan laptop backend dimatikan.
- Login demo, pastikan halaman terbuka tanpa membangunkan GPU.
- Klik Tanyakan; indikator menunggu harus muncul. Pertanyaan POST dikirim satu kali
  hanya setelah readiness berhasil. Pengulangan hanya untuk pemeriksaan GET.
- Pastikan ekspansi, 20 kandidat, jawaban bertahap, sitasi, cuplikan, dan sumber sesuai.
- Uji tiap model yang akan dipakai penguji.
- Batalkan saat pemanasan: pertanyaan belum dikirim. Ini tidak menjamin startup
  worker dihentikan; worker dapat tetap selesai memuat lalu turun sesuai idle timeout.
- Batalkan saat generasi: browser dan gerbang menutup stream. Verifikasi di log
  Runpod/Ollama bahwa pekerjaan berhenti; ini belum dibuktikan end-to-end di cloud.
- Setelah idle, pastikan worker turun ke nol; ulangi pertanyaan untuk uji cold start.
- Uji antrean penuh, model gagal, dan koneksi terputus. Jangan tampilkan traceback.
- Cek penggunaan/saldo, waktu cold start dan latency. Budget belum dipastikan.

Batas provider saat dokumentasi diperiksa: menunggu worker sekitar 2 menit dan
pemrosesan per request sekitar 5,5 menit. Halaman memeriksa kesiapan maksimum sekitar
5 menit; ini tidak memperpanjang batas provider untuk satu request.
Gerbang tidak mengulang POST agar tidak menghasilkan inferensi ganda.
Pemeriksaan kesiapan setelah startup tidak berarti bobot generasi sudah ada di VRAM:
jawaban pertama/pindah model tetap dapat memerlukan pemuatan tambahan.

Untuk demo besok, lakukan satu latihan pada kondisi dingin dan satu pada kondisi
hangat sebelum sesi. Jangan menjanjikan cold start sekian detik sebelum diukur.
Versi lokal tetap cadangan yang bisa dijalankan tanpa gerbang cloud.

## Pemeriksaan paket tanpa GPU

    python -B test_runtime.py
    node --test gateway/gateway.test.mjs gateway/connection.test.mjs
    python -B create_snapshot.py --verify

Tes ini memeriksa isolasi, gerbang, readiness dan pembatalan pada simulasi; bukan
bukti kualitas model, keberhasilan Docker build, atau kesiapan layanan Runpod.

## Rujukan resmi

- https://docs.runpod.io/serverless/load-balancing/overview
- https://docs.runpod.io/serverless/load-balancing/build-a-worker
- https://docs.runpod.io/serverless/pricing
- https://docs.runpod.io/pods/storage/types
- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/workers/configuration/secrets/
