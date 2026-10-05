"""Classify failures without exposing provider messages in HTTP responses."""
import requests

MESSAGES = {
    "model_timeout": "Model membutuhkan waktu terlalu lama. Silakan coba lagi dengan pertanyaan lebih spesifik.",
    "model_unavailable": "Layanan jawaban belum dapat dihubungi. Silakan coba beberapa saat lagi.",
    "model_missing": "Model yang dipilih belum tersedia. Silakan pilih model lain.",
    "model_memory": "Memori layanan model tidak mencukupi. Tutup aplikasi berat atau minta pengelola menyesuaikan penggunaan memori, lalu coba kembali.",
    "model_context": "Konteks yang diterima model melebihi kapasitasnya. Coba pertanyaan lebih spesifik atau pilih model lain.",
    "model_busy": "Layanan model sedang sibuk. Tunggu sebentar lalu coba kembali.",
    "model_failed": "Model gagal memproses jawaban. Coba kembali atau pilih model lain.",
    "model_stream_interrupted": "Koneksi model terputus sebelum jawaban selesai. Silakan coba kembali.",
    "model_invalid_response": "Layanan model mengirim respons yang tidak dapat dibaca. Silakan coba kembali.",
    "model_incomplete_response": "Model mencapai batas panjang sebelum menyelesaikan kalimat. Coba pertanyaan yang lebih spesifik.",
    "model_empty_response": "Model tidak menghasilkan jawaban. Silakan coba kembali atau pilih model lain.",
    "context_unavailable": "Sumber ditemukan, tetapi teksnya belum dapat dimuat dalam kapasitas model. Coba pertanyaan lebih spesifik.",
    "queue_timeout": "Waktu tunggu antrean habis. Server masih sibuk; silakan coba kembali.",
}


class InferenceError(RuntimeError):
    def __init__(self, code, diagnostic=""):
        self.code = code
        # Diagnostic stays in server logs; adapters return only the allowlisted message.
        super().__init__(f"{code}: {str(diagnostic)[:600]}")


def provider_error(message, status=None):
    text = str(message).lower()
    if any(term in text for term in ("out of memory", "not enough memory", "insufficient memory",
                                     "requires more system memory", "failed to allocate", "cannot allocate",
                                     "unable to allocate", "allocation failed", "memory allocation", "cuda malloc")):
        code = "model_memory"
    elif status == 404 or ("model" in text and "not found" in text):
        code = "model_missing"
    elif any(term in text for term in ("context length", "context window", "too many tokens", "input too long")):
        code = "model_context"
    elif status in (408, 504) or "timed out" in text or "timeout" in text:
        code = "model_timeout"
    elif status in (429, 503):
        code = "model_busy"
    else:
        code = "model_failed"
    return InferenceError(code, message)


def request_error(exc):
    if isinstance(exc, requests.Timeout) or "read timed out" in str(exc).lower():
        return InferenceError("model_timeout", type(exc).__name__)
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return InferenceError("model_stream_interrupted", type(exc).__name__)
    return InferenceError("model_unavailable", type(exc).__name__)
