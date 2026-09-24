import os
import subprocess

import requests
from huggingface_hub import hf_hub_download

from app.config import HF_TOKEN, INFERENCE_URL, MAX_NEW_TOKENS, MODEL_REGISTRY, SYSTEM_PROMPT

MODELS_DIR = "deploy/ollama_models"


def ensure_ollama_running():
    try:
        requests.get(f"{INFERENCE_URL}/api/tags", timeout=5).raise_for_status()
    except requests.RequestException:
        raise RuntimeError(f"Ollama tidak terjangkau di {INFERENCE_URL}. Jalankan 'ollama serve' dulu.")


def build_modelfile_content(gguf_path, system_role, repeat_penalty):
    abs_path = os.path.abspath(gguf_path).replace("\\", "/")
    lines = [f"FROM {abs_path}"]
    if system_role:
        lines.append(f'SYSTEM """{SYSTEM_PROMPT}"""')
    lines.append("PARAMETER temperature 0")
    lines.append(f"PARAMETER num_predict {MAX_NEW_TOKENS}")
    lines.append(f"PARAMETER repeat_penalty {repeat_penalty}")
    return "\n".join(lines)


def setup_model(key, cfg):
    gguf_path = hf_hub_download(
        repo_id=cfg["gguf_repo"],
        filename=cfg["gguf_filename"],
        token=HF_TOKEN,
        local_dir=f"{MODELS_DIR}/{key}",
    )
    content = build_modelfile_content(gguf_path, cfg["system_role"], cfg["repeat_penalty"])
    modelfile_path = f"{MODELS_DIR}/{key}/Modelfile"
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(content)

    subprocess.run(["ollama", "create", cfg["ollama_name"], "-f", modelfile_path], check=True)
    print(f"{cfg['ollama_name']} siap dipanggil via Ollama")


if __name__ == "__main__":
    ensure_ollama_running()
    for key, cfg in MODEL_REGISTRY.items():
        setup_model(key, cfg)
