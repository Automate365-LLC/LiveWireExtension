import json
import logging
from typing import List, Dict, Any

# --- CONFIGURATION ---
# Logs go to stderr so they don't interfere with JSON responses
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# UX constraint: cards should remain readable and UI-safe
MAX_BODY_LENGTH = 300


def generate_cards(transcript_window: str, retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Grounded Card Generator
    Converts retrieved chunks directly into cards to enforce zero hallucination.
    transcript_window is accepted for interface consistency but is not used in
    deterministic, source-backed generation.
    """

    # 1. [Retrieval Gate]
    # If no chunks passed WS4-2.2 thresholding, return a single generic fallback.
    if not retrieved_chunks:
        logger.info("Low confidence retrieval. Returning generic fallback card.")
        return [generate_generic_card()]

    generated_cards = []

    # 2. [Source-Backed Processing]
    # Generate up to the top 3 cards, preserving retriever order (no re-ranking).
    for i, chunk in enumerate(retrieved_chunks[:3]):

        content = chunk.get("text_content", "")
        chunk_id = chunk.get("chunk_id", "unknown")
        metadata = chunk.get("metadata", {})

        # Deterministic ID prevents frontend flicker across re-generations
        card_id = f"grounded-{chunk_id[:8]}"

        # Prefer source-aware titles when available
        title = metadata.get("source", f"Insight #{i + 1}")

        # Enforce UI-safe body length without altering semantic meaning
        if len(content) > MAX_BODY_LENGTH:
            content = content[:MAX_BODY_LENGTH] + "..."

        card = {
            "card_id": card_id,
            "title": title,
            "body": content,  # STRICT: source pass-through only
            "type": "coaching",
            "grounded": True,
            "source_chunk_ids": [chunk_id]  # Traceability is mandatory
        }

        generated_cards.append(card)

    logger.info(f"Generated {len(generated_cards)} grounded cards.")
    return generated_cards


def generate_generic_card() -> Dict[str, Any]:
    """
    [No-Source Condition]
    Minimal fallback when no relevant playbook content is retrieved.
    """
    return {
        "card_id": "generic-fallback",
        "title": "Active Listening",
        "body": "Listening for relevant playbook guidance…",
        "type": "generic",
        "grounded": False,
        "source_chunk_ids": []
    }


# --- TEST BLOCK ---
if __name__ == "__main__":
    test_chunks = [{
        "chunk_id": "uuid-1234-5678",
        "text_content": (
            "When discussing pricing, anchor high by introducing the Enterprise "
            "plan first ($500/mo) before transitioning to the Standard plan."
        ),
        "score": 1.1,
        "metadata": {"source": "Pricing_Playbook_v2.pdf"}
    }]

    print("--- Testing Generator ---")
    cards = generate_cards("How much does it cost?", test_chunks)
    print(json.dumps(cards, indent=2))
