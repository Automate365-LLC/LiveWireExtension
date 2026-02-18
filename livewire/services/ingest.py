import os
import json
import uuid
import re
import numpy as np
import faiss
from datetime import datetime
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_path

# --- CONFIGURATION ---
# All file paths are relative to this script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK_FILE = os.path.join(BASE_DIR, "..", "gold_playbook.pdf")   # input PDF
VECTOR_STORE_FILE = os.path.join(BASE_DIR, "local_vector_db.json")  # output: chunk records
INDEX_FILE = os.path.join(BASE_DIR, "vector_index.bin")             # output: FAISS vector index

# Paths to Windows OCR binaries (only used if PDF is image-based)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\vedan\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Users\vedan\poppler-25.12.0\Library\bin"

# --- MODEL (lazy-loaded) ---
# SentenceTransformer is only loaded when first needed,
# so importing this file doesn't slow down other services (e.g. FastAPI)
_model = None

def get_model():
    global _model
    if _model is None:
        print("   -> Loading embedding model...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model


# --- TEXT EXTRACTION ---
def extract_page_text(page, page_num):
    """
    Extract raw text from a single PDF page.
    - First tries pypdf (fast, works on text-based PDFs)
    - If pypdf returns nothing, the page is image-based — falls back to Tesseract OCR
    """
    text = page.extract_text()
    if text and text.strip():
        return text

    # pypdf got nothing — run OCR on this page
    print(f"   [OCR] Page {page_num} is image-based, running Tesseract...")
    try:
        # Convert just this page to a high-res image, then OCR it
        images = convert_from_path(
            PLAYBOOK_FILE, dpi=300,
            first_page=page_num, last_page=page_num,
            poppler_path=POPPLER_PATH
        )
        if images:
            return pytesseract.image_to_string(images[0], lang='eng')
    except Exception as e:
        print(f"   [OCR] ERROR on page {page_num}: {e}")

    return ""  # nothing extracted — caller will skip this page


# --- CHUNKING ---
def chunk_page_text(page_text):
    """
    Split page text into chunks ready for embedding.
    Strategy (per WS4 Arch §3.2):
      1. Split on double newlines to preserve paragraph/Q&A boundaries
      2. If a chunk > 1000 chars, reassemble line-by-line with 100-char overlap
      3. Single lines > 1000 chars are split by sentence boundaries
    """
    # Strip structural header lines (e.g. "---", "Title:") at line level
    # so we don't accidentally corrupt inline content like "price: $50---$200"
    clean_lines = [
        line for line in page_text.splitlines()
        if not line.strip().startswith("---") and not line.strip().startswith("Title:")
    ]
    page_text = "\n".join(clean_lines)

    sized_chunks = []

    # Stage 1: split on paragraph/Q&A boundaries (double newlines)
    for semantic_chunk in re.split(r'\n\n+', page_text):
        semantic_chunk = semantic_chunk.strip()
        if not semantic_chunk:
            continue

        # Chunk is within the 1000-char model limit — keep it as-is
        if len(semantic_chunk) <= 1000:
            sized_chunks.append(semantic_chunk)
            continue

        # Stage 2: chunk is too big — break it into lines and reassemble with overlap
        current_chunk = ""
        for line in re.split(r'\n', semantic_chunk):
            line = line.strip()
            if not line:
                continue

            if len(current_chunk) + len(line) + 1 <= 1000:
                # Line fits — keep building the current chunk
                current_chunk += line + " "
            else:
                # Current chunk is full — save it and start a new one
                if current_chunk.strip():
                    sized_chunks.append(current_chunk.strip())

                if len(line) > 1000:
                    # Edge case: a single line is still too long — split by sentence
                    temp_chunk = ""
                    for sent in re.split(r'(?<=[.!?]) +', line):
                        if len(temp_chunk) + len(sent) + 1 <= 1000:
                            temp_chunk += sent + " "
                        else:
                            if temp_chunk.strip():
                                sized_chunks.append(temp_chunk.strip())
                            temp_chunk = sent + " "
                    if temp_chunk.strip():
                        sized_chunks.append(temp_chunk.strip())
                    current_chunk = ""
                else:
                    # Start new chunk with last 100 chars of previous for context overlap (WS4-09)
                    overlap = current_chunk.strip()[-100:] if len(current_chunk.strip()) >= 100 else current_chunk.strip()
                    current_chunk = overlap + " " + line + " "

        # Save whatever is left in the current chunk after the loop
        if current_chunk.strip():
            sized_chunks.append(current_chunk.strip())

    return sized_chunks


# --- SECTION DETECTION ---
def detect_section(page_text):
    """
    Find the last heading on the page to use as section metadata.
    Headings are detected as: short, ALL-CAPS lines with no trailing period.
    This is used later by WS4-14 reranking to boost results from matching sections.
    """
    section = None
    for line in page_text.splitlines():
        stripped = line.strip()
        if stripped and stripped.isupper() and len(stripped) < 80 and not stripped.endswith('.'):
            section = stripped
    return section


# --- MAIN INGESTION ---
def ingest_playbook():
    if not os.path.exists(PLAYBOOK_FILE):
        print(f"ERROR: File not found at {PLAYBOOK_FILE}")
        return

    print(f"--- INGESTING: {os.path.basename(PLAYBOOK_FILE)} ---")

    database_records = []  # list of chunk dicts to save as JSON
    text_list = []         # plain text list for embedding model

    reader = PdfReader(PLAYBOOK_FILE)
    print(f"   -> {len(reader.pages)} page(s) found")

    # Process each page independently to preserve page-level metadata
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = extract_page_text(page, page_num)

        if not page_text.strip():
            print(f"   [WARN] Page {page_num}: no text extracted, skipping.")
            continue

        section = detect_section(page_text)   # heading context for this page
        chunks = chunk_page_text(page_text)   # list of clean text chunks

        for chunk in chunks:
            clean_chunk = chunk.strip()
            if len(clean_chunk) < 15:  # skip noise/fragments (e.g. lone page numbers)
                continue

            # Build the record — this is what gets saved to JSON and searched at runtime
            database_records.append({
                "chunk_id": str(uuid.uuid4()),      # unique ID for traceability (WS4-03)
                "text_content": clean_chunk,
                "metadata": {
                    "source_file": os.path.basename(PLAYBOOK_FILE),
                    "page": page_num,               # integer page number
                    "section": section,             # last heading seen on this page
                    "ingested_at": str(datetime.now())
                }
            })
            text_list.append(clean_chunk)

    if not database_records:
        print("No valid chunks found.")
        return

    # Generate embeddings and build FAISS index for vector search
    print(f"   -> {len(database_records)} chunks generated")
    print("   -> Generating embeddings...")
    embeddings = get_model().encode(text_list)

    # IndexFlatL2 = exact L2 distance search (no approximation) — correct for v0 scale
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings).astype('float32'))

    # Save chunk records (JSON) and vector index (binary) to disk
    with open(VECTOR_STORE_FILE, 'w', encoding='utf-8') as f:
        json.dump(database_records, f, indent=2)
    faiss.write_index(index, INDEX_FILE)

    # Evidence pack summary log (required by S5-WS4-1 DoD)
    print(f"--- INGESTION COMPLETE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    print(f"   -> Source:   {os.path.basename(PLAYBOOK_FILE)}")
    print(f"   -> Pages:    {len(reader.pages)}")
    print(f"   -> Chunks:   {len(database_records)}")
    print(f"   -> Outputs:  {os.path.basename(VECTOR_STORE_FILE)} + {os.path.basename(INDEX_FILE)}")


if __name__ == "__main__":
    ingest_playbook()