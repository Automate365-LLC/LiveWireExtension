import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from services.retrieve import retrieve_chunks
from services.card_generator import generate_cards
# --- CONFIGURATION ---
# Hardcoded queries for reproducible regression testing.
# Mix of Hits (expect grounded), Misses (chit-chat), and Noise (irrelevant)
TEST_CASES = [
    # --- HITS (Content exists in playbook) ---
    {"query": "How much does it cost per month?", "expect_hit": True},    
    {"query": "Do you integrate with Zapier?", "expect_hit": True},       
    {"query": "Is my data secure and SOC2 compliant?", "expect_hit": True}, # Matches "fully SOC2 compliant"
    {"query": "What is the refund policy?", "expect_hit": True},          # Matches "14-day money-back"
    
    # --- MISSES (Content NOT in playbook -> Should return Generic) ---
    {"query": "Do you integrate with Salesforce?", "expect_hit": False},  
    {"query": "Do you have an enterprise plan?", "expect_hit": False},   
    {"query": "Can I deploy this on-premise?", "expect_hit": False},      
    
    # --- NOISE (Irrelevant -> Should return Generic) ---
    {"query": "What is the weather in Tokyo?", "expect_hit": False},      
    {"query": "Tell me a joke.", "expect_hit": False},                
    {"query": "Hello, how are you today?", "expect_hit": False},            
]

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_evaluation():
    # Header for console output table
    print(f"{'QUERY':<50} | {'FOUND':<5} | {'TYPE':<15} | {'RESULT'}")
    print("-" * 90)

    passed_tests = 0
    total_hallucinations = 0
    results_log = []  # collects per-query results for replay log

    for case in TEST_CASES:
        query = case["query"]

        # --- Run pipeline ---
        chunks = list(retrieve_chunks(query))
        try:
            cards = generate_cards(query, chunks)
        except Exception as e:
            logger.error(f"Generator exception for '{query}': {e}")
            cards = []

        # --- Analyze output ---
        has_grounded = any(c.get("grounded") for c in cards)

        # --- Grading ---
        status = "FAIL"
        if case["expect_hit"]:
            if has_grounded:
                status = "PASS"
        else:
            if not has_grounded:
                status = "PASS"

        if status == "PASS":
            passed_tests += 1

        # --- Hallucination / consistency checks ---
        for card in cards:
            if card.get("grounded"):
                # Missing source IDs
                if not card.get("source_chunk_ids"):
                    total_hallucinations += 1
                    print(f"🚨 HALLUCINATION: Grounded card missing source_chunk_ids for '{query}'")
                # Check that card body exists in retrieved chunk
                snippet = card.get("body", "")[:50]
                found_in_source = any(snippet in c.get("text_content", "") for c in chunks)
                if not found_in_source and chunks:
                    total_hallucinations += 1
                    print(f"🚨 DATA MISMATCH: Card body not found in source text for '{query}'")

        # --- display for table ---
        query_display = query if len(query) <= 50 else query[:47] + "..."
        card_type = cards[0].get("type") if cards else "N/A"
        print(f"{query_display:<50} | {len(chunks):<5} | {card_type:<15} | {status}")

        # --- Build replay log entry ---
        results_log.append({
            "query": query,
            "expect_hit": case["expect_hit"],
            "chunks_found": len(chunks),
            "chunk_ids": [c["chunk_id"][:8] for c in chunks],
            "card_type": card_type,
            "grounded": has_grounded,
            "result": status,
            "source_chunk_ids": cards[0].get("source_chunk_ids", []) if cards else []
        })
        

    # --- Final summary ---
    print("-" * 90)
    print(f"Final Score: {passed_tests}/{len(TEST_CASES)}")
    print(f"Total Hallucinations Detected: {total_hallucinations}")

    if passed_tests == len(TEST_CASES):
        print("✅ All test cases passed. Grounded generator ready for downstream integration.")
    else:
        print("⚠️ Some tests failed. Review retrieval settings or playbook content.")

    # --- Save replay log as evidence ---
    log_path = os.path.join(os.path.dirname(__file__), "replay_log.json")
    replay_log = {
        "run_at": str(datetime.now()),
        "score": f"{passed_tests}/{len(TEST_CASES)}",
        "hallucinations": total_hallucinations,
        "passed": passed_tests == len(TEST_CASES),
        "results": results_log
    }
    with open(log_path, "w") as f:
        json.dump(replay_log, f, indent=2)
    print(f"\nReplay log saved → {log_path}")


if __name__ == "__main__":
    run_evaluation()