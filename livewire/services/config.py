# --- SHARED CONFIGURATION ---
# Single source of truth for constants used across WS4 services

# Grounding threshold 
# L2 distance: lower = more similar, 0 = exact match

# Tuned Feb 18 2026 against gold_playbook.pdf + all-MiniLM-L6-v2
GROUNDING_THRESHOLD = 1.25

# Embedding model — must match the model used during ingestion
# Changing this requires re-running ingest.py to rebuild the index
EMBEDDING_MODEL = "all-MiniLM-L6-v2"