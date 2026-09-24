import json

import faiss
from huggingface_hub import hf_hub_download
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from app.config import (
    EMBEDDING_MODEL_ID,
    HF_KB_REPO,
    HF_TOKEN,
    KB_CACHE_DIR,
    QUERY_PREFIX,
    RRF_K,
    TOP_K_DENSE,
    TOP_K_RERANK_CANDIDATES,
    TOP_K_SPARSE,
)


class NomicQueryEmbeddings(Embeddings):
    def __init__(self, model_id=EMBEDDING_MODEL_ID):
        self.model = SentenceTransformer(model_id, trust_remote_code=True)

    def embed_query(self, text):
        vector = self.model.encode(QUERY_PREFIX + text, normalize_embeddings=True)
        return vector.tolist()

    def embed_documents(self, texts):
        raise NotImplementedError("Dokumen sudah diembed pada NB07; tidak dipakai ulang di sini.")


def download_kb_artifacts():
    index_path = hf_hub_download(HF_KB_REPO, "faiss_index.bin", repo_type="dataset", token=HF_TOKEN, local_dir=KB_CACHE_DIR)
    metadata_path = hf_hub_download(HF_KB_REPO, "chunk_metadata.jsonl", repo_type="dataset", token=HF_TOKEN, local_dir=KB_CACHE_DIR)
    return index_path, metadata_path


def load_documents(metadata_path):
    documents = []
    with open(metadata_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            documents.append(Document(page_content=record["text"], metadata=record))
    return documents


def adapt_faiss_to_langchain(index_path, documents, embeddings):
    raw_index = faiss.read_index(index_path)

    docstore_dict = {}
    index_to_docstore_id = {}
    for doc in documents:
        faiss_id = doc.metadata["faiss_id"]
        doc_id = str(faiss_id)
        docstore_dict[doc_id] = doc
        index_to_docstore_id[faiss_id] = doc_id

    return FAISS(
        embedding_function=embeddings,
        index=raw_index,
        docstore=InMemoryDocstore(docstore_dict),
        index_to_docstore_id=index_to_docstore_id,
    )


def build_indices():
    index_path, metadata_path = download_kb_artifacts()
    documents = load_documents(metadata_path)
    embeddings = NomicQueryEmbeddings()
    vectorstore = adapt_faiss_to_langchain(index_path, documents, embeddings)
    bm25_retriever = BM25Retriever.from_documents(documents, preprocess_func=lambda text: text.lower().split())
    bm25_retriever.k = TOP_K_SPARSE
    return vectorstore, bm25_retriever


def reciprocal_rank_fusion(rankings, k=RRF_K):
    scores = {}
    doc_lookup = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            doc_id = doc.metadata["faiss_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            doc_lookup[doc_id] = doc
    ranked_ids = sorted(scores, key=scores.get, reverse=True)
    return [doc_lookup[doc_id] for doc_id in ranked_ids]


def hybrid_search(vectorstore, bm25_retriever, queries, dense_k=TOP_K_DENSE, sparse_k=TOP_K_SPARSE):
    rankings = []
    for query in queries:
        dense_docs = [doc for doc, _ in vectorstore.similarity_search_with_score(query, k=dense_k)]
        rankings.append(dense_docs)
        sparse_docs = bm25_retriever.invoke(query)[:sparse_k]
        rankings.append(sparse_docs)
    fused = reciprocal_rank_fusion(rankings)
    return fused[:TOP_K_RERANK_CANDIDATES]


def format_source(doc, score):
    m = doc.metadata
    return {
        "chunk_id": m.get("chunk_id"),
        "document_title": m.get("document_title"),
        "section_id": m.get("section_id"),
        "page_start": m.get("page_start"),
        "page_end": m.get("page_end"),
        "bps_url": m.get("bps_url"),
        "score": float(score),
    }


if __name__ == "__main__":
    vectorstore, bm25_retriever = build_indices()
    candidates = hybrid_search(vectorstore, bm25_retriever, ["Berapa jumlah penduduk miskin di Indonesia?"])
    for doc in candidates:
        print(doc.metadata.get("chunk_id"), doc.metadata.get("document_title"))
        print(doc.page_content[:200])
        print()
