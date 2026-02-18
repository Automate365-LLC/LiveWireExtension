import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import logging
import time
import functools

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_STORE_FILE = os.path.join(BASE_DIR, "local_vector_db.json")
INDEX_FILE = os.path.join(BASE_DIR, "vector_index.bin")

# Grounding threshold (WS4-2.2): L2 distance — lower = more similar, 0 = exact match
# Chunks scoring >= 1.2 are considered unrelated and filtered out
DISTANCE_THRESHOLD = 1.2

# Logger writes to stderr so it never pollutes stdout JSON (required for WS3 integration)
logging.basicConfig(
    level=logging.INFO,  # switch to DEBUG when tuning threshold
    format="%(asctime)s [WS4-RETRIEVAL] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- GLOBAL RESOURCES (lazy-loaded once, reused across all calls) ---
_model = None
_index = None
_db = None

def get_resources():
    """Load the embedding model, FAISS index, and chunk database — once per session."""
    global _model, _index, _db

    if _model is None:
        logger.info("Loading sentence transformer model")
        _model = SentenceTransformer("all-MiniLM-L6-v2")

    if _index is None and os.path.exists(INDEX_FILE):
        logger.info("Loading FAISS index")
        _index = faiss.read_index(INDEX_FILE)

    if _db is None and os.path.exists(VECTOR_STORE_FILE):
        logger.info("Loading vector database")
        with open(VECTOR_STORE_FILE, "r", encoding="utf-8") as f:
            _db = json.load(f)

    return _model, _index, _db


# --- RETRIEVAL CORE ---
def _run_retrieval(query: str, top_k: int) -> list:
    """
    Runs vector search and applies grounding threshold filter.
    Separated from the cached wrapper so lru_cache works correctly
    (lru_cache requires the decorated function to return a hashable/immutable value —
    keeping the return as a list of dicts is fine here since we don't mutate it).
    """
    model, index, db = get_resources()

    if index is None or db is None:
        logger.warning("Search aborted: index or database not loaded")
        return []

    start_time = time.perf_counter()

    # 1. Encode query into a vector and search FAISS for top-k nearest chunks
    query_vector = model.encode([query])
    D, I = index.search(np.array(query_vector).astype("float32"), top_k)

    if D.size == 0 or len(D[0]) == 0:
        return []

    results = []
    for i, idx in enumerate(I[0]):
        if idx == -1:
            continue  # FAISS returns -1 for empty slots when index has fewer than top_k items

        raw_score = float(D[0][i])

        # 2. Grounding threshold check (WS4-2.2): discard chunks that are too far away
        if raw_score >= DISTANCE_THRESHOLD:
            continue

        record = db[idx]

        # confidence + grounded are stubs until WS4-14 reranking is implemented
        results.append({
            "chunk_id": record["chunk_id"],
            "score": raw_score,       # real L2 distance from FAISS
            "confidence": 0.95,       # STUB: hardcoded until reranking built
            "grounded": True,         # STUB: assumed true if it passed threshold
            "text_content": record["text_content"],
            "metadata": record.get("metadata", {})
        })

    latency_ms = (time.perf_counter() - start_time) * 1000

    # NOTE: this only fires on cold start — cache hits bypass this function entirely
    logged_data = [{"id": r["chunk_id"][:8], "score": round(r["score"], 3)} for r in results]
    logger.info(
        f"Retrieved {len(results)} chunks | "
        f"Latency: {latency_ms:.2f}ms | "
        f"Matches: {logged_data}"
    )

    return results


# NOTE: all args must stay hashable (str, int) for lru_cache to work
# If you add workspace_id dicts or filter objects later, switch to a manual dict cache
@functools.lru_cache(maxsize=100)
def _retrieve_cached(query: str, top_k: int = 3) -> tuple:
    """
    Cached wrapper around _run_retrieval.
    Returns a tuple (not list) so lru_cache can store it safely —
    tuples are immutable and hashable, lists are not.
    """
    return tuple(_run_retrieval(query, top_k))


def retrieve_chunks(query: str, top_k: int = 3) -> list:
    """
    Public retrieval entry point (called by generate.py and the API layer).
    - Repeated queries within the same session are served instantly from cache
    - Returns a list of grounded chunk dicts, or [] if nothing meets the threshold
    - Downstream (generate.py) must treat an empty list as a fallback trigger
    """
    return list(_retrieve_cached(query, top_k))


# --- TEST BLOCK (Evidence Pack Generator) ---
if __name__ == "__main__":

    print("\n--- Query 1 (Cold Start) ---")
    res1 = retrieve_chunks("How much does it cost?", top_k=3)
    print(f"Chunks found: {len(res1)}")

    print("\n--- Query 2 (Cache Hit Proof) ---")
    start_cache = time.perf_counter()
    res2 = retrieve_chunks("How much does it cost?", top_k=3)
    cache_latency = (time.perf_counter() - start_cache) * 1000
    print(f"Cache intercepted! Returned {len(res2)} chunks in {cache_latency:.4f}ms")

    print("\n--- Query 3 (Fallback Test — not in playbook) ---")
    res3 = retrieve_chunks("What is the weather in Tokyo?", top_k=3)
    print(f"Chunks returned: {len(res3)}")
    if not res3:
        print("Correctly returned empty list — generate.py should trigger fallback card")