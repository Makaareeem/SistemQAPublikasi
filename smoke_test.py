"""Checks the deployed API; does not duplicate the application's RAG pipeline."""
import requests

def main():
    base = "http://127.0.0.1:8000"
    ready = requests.get(base + "/api/ready", timeout=10)
    ready.raise_for_status()
    response = requests.post(base + "/api/ask", json={"question": "Apa yang dimaksud TPAK?"}, timeout=600)
    response.raise_for_status()
    result = response.json()
    assert result["config"]["use_rag"] is True
    assert "answer_status" in result and "sources" in result
    print("Status:", result["answer_status"])
    print("Jawaban:", result["answer"])
    print("Waktu:", result["latency"])

if __name__ == "__main__":
    main()
