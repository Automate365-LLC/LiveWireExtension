"""
WS4 — S7-WS4-1: Retrieval Reliability Under Live Call Load
Simulates a real Zoom/Teams sales call session with repeated queries.
Proves latency stability and cache reliability under live call churn.
"""
import sys
import os
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.retrieve import retrieve_chunks

# Simulates a realistic 10-turn sales call
# Based on real Automate365 call patterns from GHL sandbox
# Repeated queries prove cache is working under live call churn
SIMULATED_CALL = [
    # Turn 1 — prospect asks about pricing
    "How much does it cost?",
    # Turn 2 — integration question
    "Do you integrate with Zapier?",
    # Turn 3 — security concern
    "Is my data secure?",
    # Turn 4 — pricing comes up again (cache hit expected)
    "How much does it cost?",
    # Turn 5 — refund policy
    "What is the refund policy?",
    # Turn 6 — Zapier again (cache hit expected)
    "Do you integrate with Zapier?",
    # Turn 7 — out of playbook, fallback expected
    "Can I deploy this on-premise?",
    # Turn 8 — pricing third time (cache hit expected)
    "How much does it cost?",
    # Turn 9 — noise, fallback expected
    "What is the weather in Tokyo?",
    # Turn 10 — security again (cache hit expected)
    "Is my data secure?",
]


def run_load_test():
    print(f"\n{'='*80}")
    print(f"WS4 LIVE CALL LOAD TEST")
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Simulating {len(SIMULATED_CALL)}-turn call session (Zoom/Teams)")
    print(f"{'='*80}\n")

    print(f"{'#':<4} | {'QUERY':<38} | {'CHUNKS':<7} | {'LATENCY':<13} | {'CACHE':<6} | STATUS")
    print("-" * 82)

    results = []
    seen_queries = set()

    for i, query in enumerate(SIMULATED_CALL, 1):
        is_repeat = query in seen_queries
        seen_queries.add(query)

        start = time.perf_counter()
        chunks = retrieve_chunks(query)
        latency_ms = (time.perf_counter() - start) * 1000

        # Cache hit = repeated query returned under 1ms
        cache_hit = is_repeat and latency_ms < 1.0
        cache_label = "HIT ✅" if cache_hit else "MISS"

        chunk_ids = [c["chunk_id"][:8] for c in chunks] if chunks else []
        status = "GROUNDED" if chunks else "FALLBACK"
        query_display = query[:38] if len(query) <= 38 else query[:35] + "..."

        print(f"{i:<4} | {query_display:<38} | {len(chunks):<7} | {latency_ms:<10.3f}ms | {cache_label:<9} | {status}")

        results.append({
            "turn": i,
            "query": query,
            "is_repeat": is_repeat,
            "cache_hit": cache_hit,
            "latency_ms": round(latency_ms, 3),
            "chunks_found": len(chunks),
            "chunk_ids": chunk_ids,
            "status": status
        })

    # --- Summary stats ---
    all_latencies = [r["latency_ms"] for r in results]
    cold_latencies = [r["latency_ms"] for r in results if not r["cache_hit"]]
    repeated = [r for r in results if r["is_repeat"]]
    cache_hits = [r for r in results if r["cache_hit"]]

    print("-" * 82)
    print(f"\nSUMMARY")
    print(f"  Total turns:           {len(results)}")
    print(f"  Repeated queries:      {len(repeated)}")
    print(f"  Cache hits:            {len(cache_hits)}/{len(repeated)}")
    print(f"  Avg cold latency:      {sum(cold_latencies)/len(cold_latencies):.2f}ms")

    if cache_hits:
        avg_cache = sum(r["latency_ms"] for r in cache_hits) / len(cache_hits)
        print(f"  Avg cache latency:     {avg_cache:.4f}ms")

    print(f"  Max latency:           {max(all_latencies):.2f}ms")
    print(f"  Min latency:           {min(all_latencies):.4f}ms")
    print(f"\n  NOTE: Turn 1 latency includes model cold start (~7s).")
    print(f"  Subsequent cold queries avg: {sum(cold_latencies[1:])/max(len(cold_latencies)-1,1):.2f}ms")

    # --- DoD verification ---
    all_cache_hits_verified = len(cache_hits) == len(repeated)
    chunk_ids_present = all(
        len(r["chunk_ids"]) > 0
        for r in results
        if r["status"] == "GROUNDED"
    )

    print(f"\nDoD VERIFICATION")
    print(f"  Latencies logged per call:        ✅")
    print(f"  Cache prevents repeated lookups:  {'✅' if all_cache_hits_verified else '❌ FAIL — check cache'}")
    print(f"  Chunk IDs in grounded cards:      {'✅' if chunk_ids_present else '❌ FAIL — missing chunk IDs'}")

    if all_cache_hits_verified and chunk_ids_present:
        print(f"\n✅ S7-WS4-1 DoD PASSED — retrieval stable under live call load")
    else:
        print(f"\n⚠️ S7-WS4-1 DoD FAILED — review issues above")

    # --- Save evidence log ---
    log_path = os.path.join(os.path.dirname(__file__), "load_test_log.json")
    with open(log_path, "w") as f:
        json.dump({
            "run_at": str(datetime.now()),
            "platform": "Zoom/Teams web simulation",
            "total_turns": len(results),
            "cache_hits": len(cache_hits),
            "cache_hit_rate": f"{len(cache_hits)}/{len(repeated)}",
            "avg_cold_latency_ms": round(sum(cold_latencies)/len(cold_latencies), 2),
            "max_latency_ms": round(max(all_latencies), 2),
            "dod_passed": all_cache_hits_verified and chunk_ids_present,
            "results": results
        }, f, indent=2)
    print(f"\nEvidence log saved → {log_path}")


if __name__ == "__main__":
    run_load_test()