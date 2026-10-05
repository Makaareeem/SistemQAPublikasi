# Build this directory only. No laptop .env is included.
# Pin OLLAMA_IMAGE to a tested digest before publishing the final demo image.
ARG OLLAMA_IMAGE=ollama/ollama:latest
FROM ${OLLAMA_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/qa-venv
ENV PATH="/opt/qa-venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 PORT_HEALTH=8081 QA_DATA_DIR=/runpod-volume
WORKDIR /srv/qa
COPY snapshot/requirements.txt ./requirements.txt
# Retrieval uses CPU; Ollama supplies its own NVIDIA runtime for generation.
RUN python -m pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && python -m pip install --no-cache-dir -r requirements.txt && python -m pip check
COPY snapshot/ ./
COPY runtime/ ./runtime/
EXPOSE 8000 8081
ENTRYPOINT ["python", "-m", "runtime.launch"]
