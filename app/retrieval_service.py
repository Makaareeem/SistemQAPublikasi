import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import faiss
import numpy as np
from huggingface_hub import hf_hub_download
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
from app.cache import TTLCache
from app.device_policy import retrieval_device
from app.config import (EMBEDDING_MODEL_ID, EMBEDDING_REVISION, EMBEDDING_DEVICE, HF_KB_REPO,
                        HF_TOKEN, KB_CACHE_DIR, KB_REVISION, QUERY_PREFIX, RRF_K,
                        TOP_K_DENSE, TOP_K_RERANK_CANDIDATES, TOP_K_SPARSE, CACHE_TTL)

KB_FINGERPRINT = ""
_vector_cache = TTLCache(256, CACHE_TTL)


def tokenize(text):
    return re.findall(r"\w+(?:[.,]\d+)*", text.casefold(), flags=re.UNICODE)


class NomicQueryEmbeddings(Embeddings):
    def __init__(self, model_id=EMBEDDING_MODEL_ID):
        self.model = SentenceTransformer(model_id, revision=EMBEDDING_REVISION,
                                         device=retrieval_device(EMBEDDING_DEVICE), trust_remote_code=True)

    def embed_queries(self, texts, use_cache=True):
        vectors, pending = {}, []
        for text in dict.fromkeys(texts):
            value = _vector_cache.get(text) if use_cache else None
            if value is None:
                pending.append(text)
            else:
                vectors[text] = value
        if pending:
            batch = self.model.encode([QUERY_PREFIX + t for t in pending],
                                      normalize_embeddings=True, show_progress_bar=False)
            for text, vector in zip(pending, batch):
                vectors[text] = vector.tolist()
                if use_cache:
                    _vector_cache.put(text, vectors[text])
        return [vectors[text] for text in texts]

    def embed_query(self, text):
        return self.embed_queries([text])[0]

    def embed_documents(self, texts):
        raise NotImplementedError("Gunakan indeks dokumen yang sudah dibangun.")


def download_kb_artifacts():
    paths = [Path(KB_CACHE_DIR) / name for name in ("faiss_index.bin", "chunk_metadata.jsonl")]
    # Stable local snapshot: no network request during ordinary restarts.
    if all(path.is_file() for path in paths):
        return tuple(str(path) for path in paths)
    return tuple(hf_hub_download(HF_KB_REPO, path.name, repo_type="dataset", token=HF_TOKEN,
                                revision=KB_REVISION, local_dir=KB_CACHE_DIR) for path in paths)


def load_documents(metadata_path):
    documents = []
    with open(metadata_path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record.get("text"), str) or not record["text"].strip():
                raise ValueError("Knowledge base memiliki teks kosong.")
            record["source_id"] = f"faiss:{record['faiss_id']}"
            documents.append(Document(page_content=record["text"], metadata=record))
    return documents


def adapt_faiss_to_langchain(index_path, documents, embeddings):
    index = faiss.read_index(index_path)
    ids = [doc.metadata["faiss_id"] for doc in documents]
    if len(ids) != index.ntotal or len(set(ids)) != len(ids) or set(ids) != set(range(index.ntotal)):
        raise ValueError("Pemetaan FAISS dan metadata tidak konsisten.")
    docstore = {str(doc.metadata["faiss_id"]): doc for doc in documents}
    return FAISS(embedding_function=embeddings, index=index,
                 docstore=InMemoryDocstore(docstore),
                 index_to_docstore_id={idx: str(idx) for idx in ids})


def build_indices():
    global KB_FINGERPRINT
    index_path, metadata_path = download_kb_artifacts()
    digest = hashlib.sha256()
    for path in (index_path, metadata_path):
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    KB_FINGERPRINT = digest.hexdigest()
    documents = load_documents(metadata_path)
    embeddings = NomicQueryEmbeddings()
    vectorstore = adapt_faiss_to_langchain(index_path, documents, embeddings)
    dimension = embeddings.model.get_sentence_embedding_dimension()
    if dimension != vectorstore.index.d:
        raise ValueError("Dimensi embedding berbeda dari indeks FAISS.")
    searchable = [d for d in documents if not d.metadata.get("is_toc")]
    if not searchable:
        raise ValueError("Tidak ada dokumen isi untuk pencarian.")
    bm25 = BM25Retriever.from_documents(searchable, preprocess_func=tokenize)
    bm25.k = TOP_K_SPARSE
    return vectorstore, bm25


def reciprocal_rank_fusion(rankings, k=RRF_K):
    scores, lookup = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, doc in enumerate(ranking, 1):
            idx = doc.metadata["faiss_id"]
            if idx in seen:
                continue
            seen.add(idx)
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
            lookup[idx] = doc
    return [lookup[idx] for idx in sorted(scores, key=scores.get, reverse=True)]


def hybrid_search(vectorstore, bm25_retriever, queries, dense_k=TOP_K_DENSE,
                  sparse_k=TOP_K_SPARSE, use_cache=True):
    queries = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
    rankings = []
    vectors = vectorstore.embedding_function.embed_queries(queries, use_cache=use_cache)
    for query, vector in zip(queries, vectors):
        dense = vectorstore.similarity_search_with_score_by_vector(vector, k=dense_k)
        rankings.append([doc for doc, _ in dense if not doc.metadata.get("is_toc")])
        scores = bm25_retriever.vectorizer.get_scores(tokenize(query))
        order = np.argsort(-scores, kind="stable")[:sparse_k]
        rankings.append([bm25_retriever.docs[int(i)] for i in order if scores[i] > 0])
    return reciprocal_rank_fusion(rankings)[:TOP_K_RERANK_CANDIDATES]


def format_source(doc, score):
    m = doc.metadata
    start = m.get("chunk_page_start") if m.get("chunk_page_start") is not None else m.get("page_start")
    end = m.get("chunk_page_end") if m.get("chunk_page_end") is not None else m.get("page_end")
    url = m.get("bps_url")
    try:
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in ("http", "https") or not parsed.hostname:
            url = None
    except ValueError:
        url = None
    return {"source_id": m.get("source_id", f"faiss:{m['faiss_id']}"),
            "chunk_id": m.get("chunk_id"), "document_title": m.get("document_title"),
            "document_year": m.get("document_year"), "section_id": m.get("section_id"),
            "page_start": start, "page_end": end if end is not None else start,
            "bps_url": url, "score": float(score)}
