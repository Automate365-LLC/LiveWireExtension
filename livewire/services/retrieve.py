import json
import os
import argparse
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import logging
import time


# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "local_vector_db.json")
INDEX_FILE = os.path.join(BASE_DIR, "vector_index.bin")

# Grounding Policy
# L2 Distance: Lower is better. 0 = Exact Match.
# Scores > 1.5 usually mean the text is unrelated.
DISTANCE_THRESHOLD = 1.2

# Logging goes to stderr by default, so it will NOT interfere with
# JSON output sent to stdout (important for WS3 integration)
logging.basicConfig(
    level=logging.INFO,  # change to DEBUG when tuning
    format="%(asctime)s [WS4-RETRIEVAL] %(levelname)s: %(message)s"
)

logger = logging.getLogger(__name__)

# Global Resources
_model = None
_index = None
_db = None

def get_resources():
    """
    load and cache the embedding model, FAISS index,
    and vector database.
    """
    global _model, _index, _db

    if _model is None:
        logger.info("Loading sentence transformer model")
        _model = SentenceTransformer("all-MiniLM-L6-v2")

    if _index is None and os.path.exists(INDEX_FILE):
        logger.info("Loading FAISS index")
        _index = faiss.read_index(INDEX_FILE)

    if _db is None and os.path.exists(DB_FILE):
        logger.info("Loading vector database")
        with open(DB_FILE, "r", encoding="utf-8") as f:
            _db = json.load(f)

    return _model, _index, _db


def retrieve_chunks(query, top_k=3):
    """
    Retrieval API and Grounding Policy Enforcement
    Returns:
        A list of grounded chunks.
        If confidence is low, returns an empty list
        so downstream systems can trigger a fallback
    """
    model, index, db = get_resources()

    # Safety check: system not initialized correctly
    if index is None or db is None:
        logger.warning("Search aborted: index or database not loaded")
        return []
    
    #Latency Timer Start
    start_time=time.perf_counter()

    # 1. VECTOR SEARCH
    query_vector = model.encode([query])
    D, I = index.search(np.array(query_vector).astype("float32"), top_k)

    if D.size == 0 or len(D[0]) == 0:
        return []

    results = []
    for i, idx in enumerate(I[0]):
        if idx == -1: continue
        
        raw_score = float(D[0][i])
        
        # Basic Threshold Check
        if raw_score >= DISTANCE_THRESHOLD:
            continue

        record = db[idx]
        
        # --- STUBBED LOGIC FOR SPRINT 3 ---
        # We return the structure the frontend expects, but with placeholder values
        # for 'confidence' and 'grounded' until the Reranking Logic is built in Sprint 4.
        results.append({
            "chunk_id": record["chunk_id"],
            "score": raw_score,            # Real Vector Score
            "confidence": 0.95,            # <--- STUB: Hardcoded for now
            "grounded": True,              # <--- STUB: Assume true if it passed threshold
            "text_content": record["text_content"],
            "metadata": record.get("metadata", {})
        })

    latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info(f"Retrieved {len(results)} chunks (Lat: {latency_ms:.2f}ms)")
    
    return results

if __name__ == "__main__":
    # Test Block
    print(json.dumps(retrieve_chunks("pricing"), indent=2))