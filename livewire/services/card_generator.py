import json
import logging
from typing import List, Dict, Any

# --- CONFIGURATION ---
# Logs go to stderr — does not interfere with JSON output sent to stdout 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Max card body length — keeps cards readable and UI-safe
MAX_BODY_LENGTH = 300

GROUNDING_THRESHOLD = 1.25  # L2 distance threshold for grounding
def generate_cards(transcript_window: str, retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    S4-WS4-3 Grounding Enforcement — converts retrieved chunks into battle cards.

    Rules (per WS4 Arch §2.5 + DoD):
      - Zero hallucination: body text comes exclusively from chunk text_content
      - If no chunks passed threshold → return 1 ungrounded fallback card with clarifying question
      - If chunks present → return 1 grounded card per chunk (max 3 for v0)
      - Every grounded card must cite its source chunk_id (traceability)
      - Ungrounded cards must be explicitly labeled grounded=False
    """

    # 1. RETRIEVAL GATE (DoD: if no relevant chunk → clarifying question, not fabricated advice)
    if not retrieved_chunks:
        logger.info("No chunks passed threshold. Returning ungrounded fallback card.")
        return [_generate_fallback_card()]

    generated_cards = []

    # 2. SOURCE-BACKED CARD GENERATION (max 3 cards for v0 — arch §2.5)
    for i, chunk in enumerate(retrieved_chunks[:3]):
        content = chunk.get("text_content", "")
        chunk_id = chunk.get("chunk_id", "unknown")
        metadata = chunk.get("metadata", {})
        raw_score = chunk.get("score", 1.0)

        # Deterministic card ID — prevents frontend flicker on re-render
        card_id = f"grounded-{chunk_id[:8]}"

        # Title priority: section heading > source filename > generic fallback
        # Uses metadata fields written by ingest.py (section + source_file)
        title = metadata.get("section") or metadata.get("source_file") or f"Insight #{i + 1}"

        # Truncate body to UI-safe length without altering meaning
        if len(content) > MAX_BODY_LENGTH:
            content = content[:MAX_BODY_LENGTH] + "..."

        # Normalize L2 distance → 0-1 confidence scale against the grounding threshold
        # score=0.0 (exact match) → 1.0 | score=threshold → 0.0 | clamped to [0, 1]
        # Using threshold as denominator avoids negative values when score is near threshold
        confidence = round(max(0.0, min(1.0, 1.0 - (raw_score / GROUNDING_THRESHOLD))), 2)

        card = {
            "card_id": card_id,
            "title": title,
            "body": content,              # STRICT: source pass-through only, no generation
            "type": "coaching",
            "grounded": True,             
            "confidence_score": confidence,
            "source_chunk_ids": [chunk_id]  # mandatory citation for traceability
        }
        generated_cards.append(card)

    logger.info(f"Generated {len(generated_cards)} grounded card(s).")
    return generated_cards


def _generate_fallback_card() -> Dict[str, Any]:
    """
    No-source fallback card (DoD: output a clarifying question, not a made-up answer).
    grounded=False and confidence_score=0.0 explicitly signal ungrounded state to WS3.
    """
    return {
        "card_id": "generic-fallback",
        "title": "Need More Context",
        "body": "I couldn't find a match in the playbook. Could you ask a clarifying question to narrow down the topic?",
        "type": "generic",
        "grounded": False,        
        "confidence_score": 0.0,  # explicit zero — no playbook backing
        "source_chunk_ids": []    # empty = no source citation
    }


# --- TEST BLOCK ---
if __name__ == "__main__":

    print("--- Test 1: Retrieval Hit (Grounded Card) ---")
    mock_chunks = [{
        "chunk_id": "uuid-1234-abcd",
        "text_content": "Pricing starts at $99/mo for the Standard plan.",
        "score": 1.219,
        "metadata": {"section": "PRICING", "source_file": "gold_playbook.pdf"}
    }]
    print(json.dumps(generate_cards("How much does it cost?", mock_chunks), indent=2))

    print("\n--- Test 2: Retrieval Miss (Fallback Card) ---")
    print(json.dumps(generate_cards("What is the weather in Tokyo?", []), indent=2))

    print("\n--- Test 3: Multiple Chunks (Max 3 cards) ---")
    multi_chunks = [
        {"chunk_id": f"uuid-000{i}", "text_content": f"Content chunk {i}.", "score": 0.3 + i * 0.1,
         "metadata": {"section": "OBJECTIONS", "source_file": "gold_playbook.pdf"}}
        for i in range(5)
    ]
    cards = generate_cards("tell me about objections", multi_chunks)
    print(f"Returned {len(cards)} cards (expected 3 max)")
    print(json.dumps(cards, indent=2))