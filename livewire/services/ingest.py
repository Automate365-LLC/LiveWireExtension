import os
import json
import uuid
import numpy as np
import faiss
from datetime import datetime
from sentence_transformers import SentenceTransformer

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK_FILE = os.path.join(BASE_DIR, "gold_playbook.txt")
DB_FILE = os.path.join(BASE_DIR, "local_vector_db.json")
INDEX_FILE = os.path.join(BASE_DIR, "vector_index.bin")

# Load AI Model 
print(" Loading AI Model (all-MiniLM-L6-v2)...")
model = SentenceTransformer('all-MiniLM-L6-v2')

def ingest_playbook():
    if not os.path.exists(PLAYBOOK_FILE):
        print(f" ERROR: File not found at {PLAYBOOK_FILE}")
        return

    print(f"---  STARTING VECTOR INGESTION: {os.path.basename(PLAYBOOK_FILE)} ---")

    with open(PLAYBOOK_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    raw_chunks = content.split('\n\n')
    database_records = []
    text_list = []

    print(f"   -> Processing {len(raw_chunks)} blocks...")

    for chunk in raw_chunks:
        clean_chunk = chunk.strip()
        if not clean_chunk or clean_chunk.startswith("---") or clean_chunk.startswith("Title:"):
            continue

        # [WS4-04] Data Model
        record = {
            "chunk_id": str(uuid.uuid4()),
            "text_content": clean_chunk,
            "metadata": {
                "source_file": "gold_playbook.txt",
                "ingested_at": str(datetime.now())
            }
        }
        database_records.append(record)
        text_list.append(clean_chunk)

    if not database_records:
        print(" No valid chunks found.")
        return

    #  Generate Embeddings & Build FAISS Index
    print("   -> Generating Vectors (Embeddings)...")
    embeddings = model.encode(text_list)
    
    # Convert to float32 for FAISS
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings).astype('float32'))

    # Save JSON (Data) + FAISS (Vectors)
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(database_records, f, indent=2)
    
    faiss.write_index(index, INDEX_FILE)

    print(f"--- SUCCESS ---")
    print(f"   -> Saved {len(database_records)} records to JSON.")
    print(f"   -> Saved FAISS Index to {os.path.basename(INDEX_FILE)}")

if __name__ == "__main__":
    ingest_playbook()