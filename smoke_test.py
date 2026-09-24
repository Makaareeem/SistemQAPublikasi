from app.config import DEFAULT_MODEL_KEY, MODEL_REGISTRY
from app.generation_service import generate, health as generation_health
from app.prompt_constructor import build_messages
from app.query_expansion_service import expand_query
from app.reranker_service import rerank
from app.retrieval_service import build_indices, hybrid_search

print("1. Ollama reachable:", generation_health())

print("2. Loading indices (dense + BM25)...")
vectorstore, bm25_retriever = build_indices()

question = "Berapa jumlah penduduk miskin di Indonesia?"
model_cfg = MODEL_REGISTRY[DEFAULT_MODEL_KEY]

print("3. Expanding query...")
expansions = expand_query(question, model_cfg)
print("   Expansions:", expansions)

print("4. Hybrid search + rerank...")
candidates = hybrid_search(vectorstore, bm25_retriever, [question] + expansions)
docs_scores, _ = rerank(question, candidates, top_k=3)
print(f"   Retrieved {len(docs_scores)} chunks, top score: {docs_scores[0][1] if docs_scores else 'N/A'}")

docs = [doc for doc, _ in docs_scores]
messages = build_messages(question, docs, system_role=model_cfg["system_role"])

print(f"5. Generating with {model_cfg['ollama_name']}...")
answer = generate(model_cfg["ollama_name"], messages, repeat_penalty=model_cfg["repeat_penalty"])
print("   Answer:", answer[:200])

print("\nSemua modul berfungsi.")
