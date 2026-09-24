import os

from dotenv import load_dotenv

load_dotenv()


def get_hf_token():
    token = os.environ.get("HF_Faiss")
    if token is None:
        raise RuntimeError("HF_TOKEN tidak ditemukan.")
    return token


HF_TOKEN = get_hf_token()
INFERENCE_URL = os.environ.get("INFERENCE_URL", "http://localhost:11434")
KB_CACHE_DIR = os.environ.get("KB_CACHE_DIR", "./app/kb_cache")

HF_KB_REPO = "Makaareeem/publikasi-rag-knowledge-base"
EMBEDDING_MODEL_ID = "nomic-ai/nomic-embed-text-v1.5"
QUERY_PREFIX = "search_query: "

RETRIEVAL_K = 5
TOP_K_DENSE = 20
TOP_K_SPARSE = 20
TOP_K_RERANK_CANDIDATES = 20
RRF_K = 60
MAX_NEW_TOKENS = 512
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
QUEUE_CONCURRENCY = int(os.environ.get("QUEUE_CONCURRENCY", "1"))

RERANKER_MODEL_ID = "madebyaris/rerank-indonesia"
RERANK_SCORE_THRESHOLD = float(os.environ.get("RERANK_SCORE_THRESHOLD", "-1.0"))

QUERY_EXPANSION_TEMPERATURE = 0.3
QUERY_EXPANSION_MAX_TOKENS = 80
QUERY_EXPANSION_SYSTEM_PROMPT = (
    "Tugas Anda: tulis ulang SATU pertanyaan menjadi SATU kalimat pencarian yang lebih deskriptif "
    "untuk sistem pencarian dokumen statistik BPS. "
    "ATURAN KETAT — WAJIB DIIKUTI: "
    "1. Output HANYA kalimat hasil tulis ulang. Tanpa kata pembuka, tanpa basa-basi, tanpa tanda kutip, "
    "tanpa penjelasan tambahan. "
    "2. JANGAN menjawab pertanyaannya. JANGAN menyebutkan angka atau fakta spesifik apa pun. "
    "3. JANGAN berkomentar tentang teks atau dokumen (dilarang keras memakai frasa seperti "
    '"teks menyatakan", "berdasarkan teks", "dokumen menyebutkan"). '
    '4. JANGAN memulai dengan basa-basi asisten (dilarang keras memakai frasa seperti "tentu saja", '
    '"tentu", "baik", "saya dapat membantu"). '
    "5. Maksimal 1 kalimat. Boleh tambahkan istilah/singkatan resmi BPS yang relevan bila ada.\n\n"
    "Contoh:\n"
    "Pertanyaan: TPAK berapa?\n"
    "Hasil: Data Tingkat Partisipasi Angkatan Kerja (TPAK) penduduk Indonesia.\n"
    "Pertanyaan: berapa kemiskinan 2024?\n"
    "Hasil: Angka dan persentase penduduk miskin di Indonesia tahun 2024."
)

CITATION_MAX_TOKENS = 500
CITATION_SYSTEM_PROMPT = (
    "Anda membantu merangkum jawaban singkat berdasarkan tiap sumber dokumen statistik BPS yang diberikan. "
    "Untuk SETIAP sumber bernomor, tulis satu kalimat yang menjawab pertanyaan HANYA berdasarkan isi sumber "
    'tersebut. Jika sumber itu tidak relevan/tidak menjawab pertanyaan, tulis "Sumber ini tidak membahas '
    'pertanyaan tersebut." Jangan mencampur informasi antar sumber. Jawab HANYA dalam format JSON: '
    '{"sources": [{"index": <nomor>, "answer": "<kalimat>"}, ...]}'
)

SYSTEM_PROMPT = (
    "Anda adalah asisten yang menjawab pertanyaan seputar publikasi statistik BPS "
    "berdasarkan konteks yang diberikan. Kutip bagian konteks yang relevan sebelum menjawab, "
    "merujuk sumber HANYA dengan nomor sitasi seperti [1] [2], jangan menyebut ulang judul "
    "dokumen dalam kalimat jawaban karena berisiko salah mengaitkan dengan sumber lain. "
    "HANYA gunakan angka atau fakta yang secara eksplisit tertulis dalam konteks yang diberikan. "
    "JANGAN menambahkan angka dari pengetahuan Anda sendiri walau terasa familiar atau masuk akal. "
    "Jika konteks memuat TARGET, RENCANA, atau PROYEKSI (misalnya dari RPJMN atau sasaran kebijakan), "
    "jelaskan dengan jelas bahwa itu adalah target/rencana, BUKAN angka realisasi atau hasil pengukuran "
    "aktual, dan jangan menyamakan keduanya. "
    "Jika konteks yang diberikan tidak memuat informasi yang relevan dengan pertanyaan, "
    "katakan dengan jujur bahwa Anda tidak memiliki informasi tersebut dalam dokumen yang tersedia. "
    "Jangan mengarang jawaban atau menyimpulkan sesuatu yang tidak didukung oleh konteks."
)

MODEL_REGISTRY = {
    "llama3.2-base": {"ollama_name": "llama3.2-base", "gguf_repo": "Makaareeem/llama3.2-base-gguf", "gguf_filename": "Llama-3.2-3B-Instruct.Q4_K_M.gguf", "system_role": True, "repeat_penalty": 1.0},
    "llama3.2-finetuned": {"ollama_name": "llama3.2-finetuned", "gguf_repo": "Makaareeem/llama3.2-finetuned-gguf", "gguf_filename": "Llama-3.2-3B-Instruct.Q4_K_M.gguf", "system_role": True, "repeat_penalty": 1.0},
    "gemma2-base": {"ollama_name": "gemma2-base", "gguf_repo": "Makaareeem/gemma2-base-gguf", "gguf_filename": "gemma-2-2b-it.Q4_K_M.gguf", "system_role": False, "repeat_penalty": 1.0},
    "gemma2-finetuned": {"ollama_name": "gemma2-finetuned", "gguf_repo": "Makaareeem/gemma2-finetuned-gguf", "gguf_filename": "gemma-2-2b-it.Q4_K_M.gguf", "system_role": False, "repeat_penalty": 1.0},
}
DEFAULT_MODEL_KEY = "llama3.2-finetuned"
