"use strict";

const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const OUT = process.argv[2];
if (!OUT) throw new Error("Output directory is required");
fs.mkdirSync(OUT, { recursive: true });

const C = {
  ink: "#243443", muted: "#617181", line: "#AAB7C2", white: "#FFFFFF",
  blue: "#2F5F8A", blueFill: "#EAF2F8",
  green: "#4F873F", greenFill: "#EEF6EA",
  orange: "#D36A24", orangeFill: "#FFF1E8",
  gold: "#B98508", goldFill: "#FFF7DB",
  slate: "#536678", slateFill: "#F3F6F8"
};

const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const lines = (arr, x, y, size = 34, weight = 500, color = C.ink, anchor = "middle", gap = 1.23) => {
  const items = Array.isArray(arr) ? arr : [arr];
  return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="Arial, Segoe UI, sans-serif" font-size="${size}" font-weight="${weight}" fill="${color}">${items.map((t, i) => `<tspan x="${x}" dy="${i ? size * gap : 0}">${esc(t)}</tspan>`).join("")}</text>`;
};
const rect = (x, y, w, h, fill, stroke, r = 20, sw = 3) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
const box = (x, y, w, h, title, body, color, fill, opts = {}) => {
  const bodyArr = Array.isArray(body) ? body : [body];
  const titleY = y + (opts.titleY || 48);
  const bodyY = y + (opts.bodyY || 94);
  return rect(x, y, w, h, fill, color, opts.radius || 18, opts.strokeWidth || 3) +
    lines(title, x + w / 2, titleY, opts.titleSize || 34, 700, color) +
    lines(bodyArr, x + w / 2, bodyY, opts.bodySize || 28, 450, C.ink, "middle", opts.gap || 1.18);
};
const arrow = (x1, y1, x2, y2, color = C.blue, dashed = false, width = 5, marker = "arrow") => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${width}" ${dashed ? 'stroke-dasharray="18 14"' : ""} marker-end="url(#${marker})"/>`;
const label = (text, x, y, color = C.muted, size = 27) => lines(text, x, y, size, 600, color);
const base = (title, body, width = 2600, height = 1500) => `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="${C.blue}"/></marker>
  <marker id="greenArrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="${C.green}"/></marker>
  <marker id="orangeArrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="${C.orange}"/></marker>
</defs>
<rect width="100%" height="100%" fill="#FFFFFF"/>
${lines(title, width / 2, 82, 58, 700, C.ink)}
${body}
</svg>`;

async function write(name, svg) {
  const svgPath = path.join(OUT, `${name}.svg`);
  const pngPath = path.join(OUT, `${name}.png`);
  fs.writeFileSync(svgPath, svg, "utf8");
  await sharp(Buffer.from(svg), { density: 180 }).png().toFile(pngPath);
}

function overview() {
  let s = "";
  s += rect(85, 120, 2430, 1290, "#FBFCFD", C.slate, 28, 4);
  s += lines("LINGKUNGAN LAPTOP LOKAL", 130, 175, 27, 700, C.slate, "start");
  s += box(220, 230, 2160, 220, "1  Client Frontend", ["Browser menjalankan HTML, CSS, dan JavaScript", "Input: pertanyaan, model, gaya jawaban | Output: proses, jawaban, dan sumber"], C.gold, C.goldFill, { titleSize: 40, bodySize: 29, bodyY: 105 });
  s += box(220, 565, 2160, 330, "2  API Server FastAPI melalui Uvicorn", ["Endpoint JSON dan SSE | validasi | antrean | pembatalan", "orkestrasi pipeline | penyusunan prompt | pemeriksaan bukti", "cache aplikasi | health dan readiness | penyajian frontend statis"], C.blue, C.blueFill, { titleSize: 40, bodySize: 29, bodyY: 112 });
  s += box(180, 1060, 1050, 255, "3  Retrieval and Knowledge Service", ["Nomic Embed - FAISS - BM25", "RRF - cross-encoder reranker", "faiss_index.bin dan chunk_metadata.jsonl"], C.green, C.greenFill, { titleSize: 36, bodySize: 27, bodyY: 100 });
  s += box(1370, 1060, 1050, 255, "4  Inference Service", ["Ollama pada 127.0.0.1:11434", "model GGUF Llama 3.2 dan Gemma 2", "ekspansi pertanyaan dan generasi jawaban"], C.orange, C.orangeFill, { titleSize: 36, bodySize: 27, bodyY: 100 });
  s += arrow(1300, 450, 1300, 565, C.blue, false, 6); s += label("HTTP lokal", 1420, 525, C.blue);
  s += arrow(770, 895, 770, 1060, C.green, false, 6, "greenArrow"); s += label("query dan chunk", 890, 990, C.green);
  s += arrow(1830, 895, 1830, 1060, C.orange, false, 6, "orangeArrow"); s += label("prompt dan token", 1975, 990, C.orange);
  s += lines("Retrieval Service dan Inference Service tidak berkomunikasi langsung; FastAPI menjadi pusat koordinasi.", 1300, 1380, 26, 500, C.muted);
  return base("Arsitektur Sistem QA RAG pada Lingkungan Lokal", s, 2600, 1480);
}

function sequence() {
  let s = "";
  const xs = [260, 880, 1580, 2290];
  const heads = [
    ["Client", "Browser dan JavaScript", C.gold, C.goldFill],
    ["API Server", "FastAPI melalui Uvicorn", C.blue, C.blueFill],
    ["Retrieval and Knowledge", "FAISS - BM25 - RRF - reranker", C.green, C.greenFill],
    ["Inference Service", "Ollama dan model GGUF", C.orange, C.orangeFill]
  ];
  heads.forEach((h, i) => { s += box(xs[i] - 245, 125, 490, 150, h[0], h[1], h[2], h[3], { titleSize: 31, bodySize: 24, bodyY: 104 }); s += `<line x1="${xs[i]}" y1="275" x2="${xs[i]}" y2="1380" stroke="#B6C0C8" stroke-width="3"/>`; });
  const flow = (y, a, b, txt, color, dashed = false, marker = "arrow") => { s += arrow(xs[a] + (a < b ? 20 : -20), y, xs[b] + (a < b ? -20 : 20), y, color, dashed, 5, marker); s += label(txt, (xs[a] + xs[b]) / 2, y - 22, color, 25); };
  flow(350, 0, 1, "1  POST /api/ask/stream: pertanyaan, model, dan gaya", C.blue);
  s += box(635, 400, 490, 135, "Validasi dan antrean", ["kesiapan - batas masukan", "slot aktif - pembatalan"], C.blue, C.blueFill, { titleSize: 27, bodySize: 22, bodyY: 82 });
  flow(600, 1, 3, "2  Permintaan perluasan pertanyaan", C.orange, false, "orangeArrow");
  flow(680, 3, 1, "hasil perluasan yang telah dibatasi", C.orange, true, "orangeArrow");
  flow(790, 1, 2, "3  Pertanyaan asli dan perluasan", C.green, false, "greenArrow");
  s += box(1335, 835, 490, 155, "Pencarian sumber", ["embedding - FAISS - BM25", "RRF - reranking - batas konteks"], C.green, C.greenFill, { titleSize: 27, bodySize: 22, bodyY: 84 });
  flow(1040, 2, 1, "4  Maksimal lima chunk beserta metadata", C.green, true, "greenArrow");
  flow(1145, 1, 3, "5  Prompt, konteks, instruksi, dan parameter", C.orange, false, "orangeArrow");
  flow(1225, 3, 1, "6  Token jawaban dan metrik inferensi", C.orange, true, "orangeArrow");
  flow(1305, 1, 0, "token sementara melalui SSE", C.blue, true, "arrow");
  s += lines("FastAPI memeriksa sitasi dan angka, lalu mengirim jawaban akhir, status, waktu, serta sumber melalui peristiwa done.", 1300, 1425, 25, 500, C.muted);
  return base("Alur Komunikasi Satu Pertanyaan", s, 2600, 1480);
}

function backend() {
  let s = "";
  s += box(95, 145, 430, 150, "Uvicorn", ["ASGI server lokal", "127.0.0.1:8000"], C.slate, C.slateFill, { bodySize: 25, bodyY: 95 });
  s += arrow(525, 220, 690, 220, C.blue, false, 6);
  s += box(690, 125, 1815, 220, "main.py  Lapisan HTTP dan siklus hidup", ["GET /api/health | GET /api/ready | POST /api/ask | POST /api/ask/stream", "startup: muat indeks dan reranker | shutdown: tutup antrean | sajikan frontend statis"], C.blue, C.blueFill, { titleSize: 38, bodySize: 26, bodyY: 108 });
  s += box(120, 440, 530, 210, "Validasi permintaan", ["schemas.py", "question_validation.py", "model - top_k - gaya - panjang"], C.gold, C.goldFill, { titleSize: 32, bodySize: 25, bodyY: 98 });
  s += box(780, 440, 530, 210, "JobRunner", ["antrean terbatas", "thread pool dan semaphore", "heartbeat - cancel - request ID"], C.blue, C.blueFill, { titleSize: 32, bodySize: 25, bodyY: 98 });
  s += box(1440, 440, 530, 210, "pipeline.py", ["orkestrasi satu pertanyaan", "status proses dan waktu", "payload akhir JSON atau SSE"], C.blue, C.blueFill, { titleSize: 32, bodySize: 25, bodyY: 98 });
  s += box(2100, 440, 380, 210, "Kontrol umum", ["config.py", "cache.py", "inference_errors.py"], C.slate, C.slateFill, { titleSize: 32, bodySize: 24, bodyY: 98 });
  s += arrow(955, 345, 385, 440, C.blue, false, 5); s += arrow(1210, 345, 1045, 440, C.blue, false, 5); s += arrow(1550, 345, 1705, 440, C.blue, false, 5); s += arrow(1910, 345, 2290, 440, C.blue, false, 5);
  s += box(110, 800, 465, 245, "Ekspansi query", ["query_expansion_service.py", "panggilan Ollama", "validasi dan cache hasil"], C.orange, C.orangeFill, { titleSize: 31, bodySize: 24, bodyY: 100 });
  s += box(660, 800, 465, 245, "Retrieval", ["retrieval_service.py", "reranker_service.py", "chunk dan metadata"], C.green, C.greenFill, { titleSize: 31, bodySize: 24, bodyY: 100 });
  s += box(1210, 800, 465, 245, "Penyusunan prompt", ["prompt_constructor.py", "fit_context", "maksimal lima sumber"], C.blue, C.blueFill, { titleSize: 31, bodySize: 24, bodyY: 100 });
  s += box(1760, 800, 465, 245, "Generasi jawaban", ["generation_service.py", "answer_stream.py", "token dan metrik Ollama"], C.orange, C.orangeFill, { titleSize: 31, bodySize: 24, bodyY: 100 });
  s += box(925, 1165, 750, 210, "Pemeriksaan keluaran", ["evidence.py memeriksa sitasi dan angka", "cuplikan sumber dipilih dari teks chunk", "status basic_checks_passed atau needs_review"], C.blue, C.blueFill, { titleSize: 32, bodySize: 24, bodyY: 98 });
  [342, 892, 1442, 1992].forEach(x => s += arrow(1705, 650, x, 800, x === 892 ? C.green : x === 342 || x === 1992 ? C.orange : C.blue, false, 5, x === 892 ? "greenArrow" : x === 342 || x === 1992 ? "orangeArrow" : "arrow"));
  s += arrow(1992, 1045, 1480, 1165, C.blue, false, 5); s += arrow(1442, 1045, 1300, 1165, C.blue, false, 5);
  return base("Rincian Komponen API Server dan Backend", s, 2600, 1450);
}

function retrieval() {
  let s = "";
  s += box(90, 150, 540, 175, "Masukan", ["pertanyaan asli", "dan satu perluasan valid"], C.blue, C.blueFill, { bodySize: 27, bodyY: 105 });
  s += arrow(630, 237, 790, 237, C.green, false, 6, "greenArrow");
  s += box(790, 130, 520, 215, "Pra-pemrosesan", ["hapus duplikasi query", "search_query: + teks", "tokenisasi huruf dan angka"], C.green, C.greenFill, { bodySize: 25, bodyY: 100 });
  s += arrow(1050, 345, 670, 520, C.green, false, 5, "greenArrow");
  s += arrow(1050, 345, 1430, 520, C.green, false, 5, "greenArrow");
  s += box(190, 520, 960, 265, "Jalur Dense", ["Nomic Embed Text v1.5", "embedding query dinormalisasi", "pencarian FAISS maksimal 20 hasil", "chunk daftar isi dikeluarkan"], C.green, C.greenFill, { titleSize: 35, bodySize: 25, bodyY: 102 });
  s += box(1270, 520, 960, 265, "Jalur Sparse", ["BM25 dibangun di memori saat startup", "tokenisasi pertanyaan", "maksimal 20 hasil dengan skor positif", "menggunakan teks chunk lokal"], C.green, C.greenFill, { titleSize: 35, bodySize: 25, bodyY: 102 });
  s += box(70, 970, 650, 320, "Domain Knowledge Lokal", ["faiss_index.bin", "chunk_metadata.jsonl", "teks - faiss_id - chunk_id", "judul - tahun - bagian", "halaman - tautan publikasi BPS"], C.slate, C.slateFill, { titleSize: 34, bodySize: 24, bodyY: 102 });
  s += arrow(670, 785, 1090, 900, C.green, false, 5, "greenArrow"); s += arrow(1750, 785, 1510, 900, C.green, false, 5, "greenArrow");
  s += box(850, 875, 900, 190, "Reciprocal Rank Fusion", ["menggabungkan daftar dense dan sparse", "RRF k = 60 | maksimal 20 kandidat unik"], C.green, C.greenFill, { titleSize: 34, bodySize: 25, bodyY: 106 });
  s += arrow(1300, 1065, 1300, 1135, C.green, false, 5, "greenArrow");
  s += box(850, 1135, 900, 190, "Cross Encoder Reranker", ["madebyaris/rerank-indonesia", "menilai pertanyaan asli terhadap setiap chunk"], C.green, C.greenFill, { titleSize: 34, bodySize: 25, bodyY: 106 });
  s += arrow(1750, 1230, 1900, 1230, C.green, false, 5, "greenArrow");
  s += box(1900, 1095, 620, 265, "Keluaran ke Pipeline", ["saring berdasarkan ambang skor", "fit_context tanpa memotong chunk", "maksimal top_k = 5", "chunk, skor, dan metadata sumber"], C.blue, C.blueFill, { titleSize: 34, bodySize: 24, bodyY: 102 });
  s += arrow(720, 1130, 850, 1010, C.slate, true, 4, "arrow");
  return base("Alur Retrieval and Knowledge Service", s, 2600, 1430);
}

function inference() {
  let s = "";
  s += box(80, 150, 600, 220, "FastAPI", ["generation_service.py", "koneksi HTTP digunakan ulang", "timeout dan penanganan kesalahan"], C.blue, C.blueFill, { titleSize: 37, bodySize: 25, bodyY: 105 });
  s += box(1920, 150, 600, 220, "Ollama Health", ["GET /api/tags", "model_status()", "daftar model yang tersedia"], C.orange, C.orangeFill, { titleSize: 37, bodySize: 25, bodyY: 105 });
  s += box(850, 120, 900, 310, "Ollama Runtime Inferensi Lokal", ["http://127.0.0.1:11434", "POST /api/chat", "pemuatan model - tokenisasi - CPU atau GPU", "stream JSON per token - metrik inferensi"], C.orange, C.orangeFill, { titleSize: 40, bodySize: 27, bodyY: 112 });
  s += arrow(680, 260, 850, 260, C.orange, false, 6, "orangeArrow");
  s += arrow(1920, 330, 1750, 330, C.orange, true, 5, "orangeArrow");
  s += box(130, 600, 720, 300, "Pemakaian 1  Ekspansi Query", ["instruksi perluasan dan pertanyaan asli", "temperature 0 | maksimal 120 token", "hasil dikumpulkan lalu divalidasi", "gagal atau tidak valid: gunakan pertanyaan asli"], C.gold, C.goldFill, { titleSize: 34, bodySize: 24, bodyY: 108 });
  s += box(940, 600, 720, 300, "Pemakaian 2  Generasi Jawaban", ["prompt berisi instruksi, sumber, dan pertanyaan", "ringkas: maksimal 150 token", "detail: maksimal 384 token", "token dikirim bertahap ke pipeline"], C.orange, C.orangeFill, { titleSize: 34, bodySize: 24, bodyY: 108 });
  s += box(1750, 600, 720, 300, "Model GGUF yang Terdaftar", ["Llama 3.2 3B dasar dan fine-tuned", "Gemma 2 2B dasar dan fine-tuned", "kuantisasi Q4_K_M", "model bawaan: Llama 3.2 fine-tuned"], C.orange, C.orangeFill, { titleSize: 34, bodySize: 24, bodyY: 108 });
  s += arrow(1300, 430, 490, 600, C.orange, false, 5, "orangeArrow"); s += arrow(1300, 430, 1300, 600, C.orange, false, 5, "orangeArrow"); s += arrow(1300, 430, 2110, 600, C.orange, false, 5, "orangeArrow");
  s += box(290, 1080, 2020, 230, "Parameter Runtime Bawaan", ["temperature 0 | seed 42 | num_ctx 8192 | num_batch 128 | keep_alive 15 menit", "num_gpu -1 menyerahkan penempatan CPU atau GPU kepada Ollama | repeat_penalty mengikuti registri model", "Ollama dan FastAPI berjalan sebagai proses terpisah tetapi tetap pada laptop lokal yang sama"], C.slate, C.slateFill, { titleSize: 34, bodySize: 25, bodyY: 105 });
  s += arrow(1300, 900, 1300, 1080, C.orange, false, 5, "orangeArrow");
  return base("Alur Inference Service Berbasis Ollama", s, 2600, 1400);
}

function frontend() {
  let s = "";
  s += box(90, 145, 470, 230, "Berkas Tampilan", ["index.html", "styles.css", "struktur semantik", "responsif desktop dan seluler"], C.gold, C.goldFill, { titleSize: 34, bodySize: 24, bodyY: 102 });
  s += box(665, 145, 585, 230, "Berkas Logika", ["app.js", "question-validation.js", "question-rules.json", "api-config.js"], C.gold, C.goldFill, { titleSize: 34, bodySize: 24, bodyY: 102 });
  s += box(1355, 145, 1155, 230, "Komponen Antarmuka", ["status layanan | kolom pertanyaan | pilihan model | gaya ringkas atau detail", "tombol Tanyakan dan Batalkan | panel proses | jawaban | catatan", "tabel kandidat | kartu sumber | publikasi terkait | panduan"], C.gold, C.goldFill, { titleSize: 34, bodySize: 24, bodyY: 102 });
  s += arrow(560, 260, 665, 260, C.gold, false, 5, "arrow"); s += arrow(1250, 260, 1355, 260, C.gold, false, 5, "arrow");
  s += box(110, 540, 430, 180, "1  Inisialisasi", ["GET /api/health", "status dan model tersedia"], C.blue, C.blueFill, { titleSize: 30, bodySize: 24, bodyY: 103 });
  s += box(620, 540, 430, 180, "2  Masukan", ["validasi awal di browser", "pertanyaan - model - gaya"], C.gold, C.goldFill, { titleSize: 30, bodySize: 24, bodyY: 103 });
  s += box(1130, 540, 430, 180, "3  Permintaan", ["POST /api/ask/stream", "AbortController"], C.blue, C.blueFill, { titleSize: 30, bodySize: 24, bodyY: 103 });
  s += box(1640, 540, 430, 180, "4  Konsumsi SSE", ["parseFrame dan consumeStream", "heartbeat - status - token"], C.blue, C.blueFill, { titleSize: 30, bodySize: 24, bodyY: 103 });
  s += box(2150, 540, 350, 180, "5  Render", ["DOM diperbarui", "tanpa muat ulang"], C.gold, C.goldFill, { titleSize: 30, bodySize: 24, bodyY: 103 });
  s += arrow(540, 630, 620, 630, C.blue, false, 5); s += arrow(1050, 630, 1130, 630, C.blue, false, 5); s += arrow(1560, 630, 1640, 630, C.blue, false, 5); s += arrow(2070, 630, 2150, 630, C.blue, false, 5);
  s += box(140, 930, 540, 280, "Status Proses", ["queued - expanding - expanded", "retrieving - reranked - sources", "generating - token - answer - done", "error dan heartbeat"], C.blue, C.blueFill, { titleSize: 34, bodySize: 24, bodyY: 104 });
  s += box(760, 930, 540, 280, "Jawaban", ["token provisional", "jawaban akhir dengan sitasi", "status pemeriksaan", "waktu dan identitas permintaan"], C.gold, C.goldFill, { titleSize: 34, bodySize: 24, bodyY: 104 });
  s += box(1380, 930, 540, 280, "Sumber", ["judul dan tahun publikasi", "halaman dan skor relevansi", "tautan publikasi BPS", "cuplikan asli dan teks lengkap"], C.green, C.greenFill, { titleSize: 34, bodySize: 24, bodyY: 104 });
  s += box(2000, 930, 480, 280, "Kendali Pengguna", ["Batalkan permintaan", "buka atau tutup panel", "menu Cara pakai", "menu Cara kerja"], C.slate, C.slateFill, { titleSize: 34, bodySize: 24, bodyY: 104 });
  s += arrow(2325, 720, 410, 930, C.blue, false, 4); s += arrow(2325, 720, 1030, 930, C.gold, false, 4); s += arrow(2325, 720, 1650, 930, C.green, false, 4, "greenArrow"); s += arrow(2325, 720, 2240, 930, C.slate, false, 4);
  s += lines("Frontend hanya berkomunikasi dengan FastAPI; alamat Ollama dan basis pengetahuan tidak diekspos kepada browser.", 1300, 1360, 26, 500, C.muted);
  return base("Rincian Komponen dan Alur Frontend", s, 2600, 1410);
}

(async () => {
  await write("figure_4_15_architecture_overview", overview());
  await write("figure_4_16_question_sequence", sequence());
  await write("figure_4_17_backend_detail", backend());
  await write("figure_4_18_retrieval_detail", retrieval());
  await write("figure_4_19_inference_detail", inference());
  await write("figure_4_20_frontend_detail", frontend());
  console.log(`Generated diagrams in ${OUT}`);
})().catch(err => { console.error(err); process.exit(1); });

