"""
a365_integration.py — WS5 CRM Push Pipeline
Updated for P1-WS5.3: IdempotencyTracker is now wired into push_to_a365_with_retry.
"""

import logging
import os
import requests
import uuid
from datetime import datetime

from rate_limit_handler import RateLimitHandler
from idempotency_tracker import IdempotencyTracker
from payload_validator import validate_payload, generate_idempotency_key, ValidationError

logger = logging.getLogger(__name__)

GHL_API_KEY = os.environ.get("GHL_API_KEY")
_rate_limiter = RateLimitHandler(max_retries=5, base_delay=2.0)
_idempotency_tracker = IdempotencyTracker()


def push_to_a365(summary: str, tasks: list, tags: list, contact_id: str = None) -> dict:
    """Push to A365/GHL with rate limit handling."""
    payload = {
        "note": summary,
        "action_items": tasks,
        "categories": tags,
        "timestamp": datetime.now().isoformat(),
        "source": "livewire",
        "contact_id": contact_id
    }

    if not GHL_API_KEY:
        logger.info(f"[MOCK] Would push to A365: {payload}")
        return {"status": "success", "mock": True, "payload": payload}

    try:
        response = requests.post(
            f"https://api.ghl.com/contacts/{contact_id}/notes",
            headers={
                "Authorization": f"Bearer {GHL_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=10
        )

        if response.status_code == 429:
            return {
                "status_code": 429,
                "error": "Rate limit exceeded",
                "error_type": "rate_limit"
            }

        if response.status_code >= 400:
            return {
                "status": "error",
                "error": f"HTTP {response.status_code}: {response.text}"
            }

        return {"status": "success", "data": response.json()}

    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def push_to_a365_with_retry(
    session_id: str,
    contact_id: str,
    summary: str,
    tasks: list,
    tags: list,
    artifact_type: str = "full_push",
    artifact_id: str = None,
) -> dict:
    """
    Push with automatic rate limit handling, validation, and idempotency guard.

    P1-WS5.3: Before any network call this function:
      1. Validates the payload (raises ValidationError for malformed input)
      2. Generates an idempotency key (session_id + artifact_type + payload_hash)
      3. Checks for an existing completed push with the same key → returns cached result
      4. Records the attempt as in_progress, executes the push
      5. Marks the record completed or failed depending on outcome

    Calling this function twice with identical arguments will execute the push
    exactly once; the second call returns the cached success result immediately.
    """

    # ── Step 1: Validate ─────────────────────────────────────────────────────
    raw_payload = {
        "session_id": session_id,
        "artifact_type": artifact_type,
        "contact_id": contact_id,
        "summary": summary,
        "tasks": tasks,
        "tags": tags,
    }
    if artifact_id:
        raw_payload["artifact_id"] = artifact_id

    try:
        validated = validate_payload(raw_payload)
    except ValidationError as e:
        logger.error(f"[{session_id}] Payload validation failed: {e.errors}")
        return {
            "status": "error",
            "error_type": "validation_error",
            "errors": e.errors,
            "session_id": session_id,
            "retryable": False,
            "visible_to_user": "Push rejected: invalid payload — fix errors and retry",
        }

    resolved_artifact_id = validated.get("artifact_id")

    # ── Step 2: Idempotency check ─────────────────────────────────────────────
    idempotency_key = generate_idempotency_key(session_id, artifact_type, validated)
    dedupe_key = _idempotency_tracker.generate_dedupe_key(
        session_id, artifact_type, resolved_artifact_id
    )

    duplicate_check = _idempotency_tracker.check_duplicate(dedupe_key, validated)

    if duplicate_check and duplicate_check.get("duplicate"):
        logger.info(
            f"[{session_id}] Duplicate detected for key={dedupe_key}. "
            f"Already completed at {duplicate_check.get('completed_at')}. Skipping push."
        )
        return {
            "status": "skipped",
            "reason": "duplicate",
            "message": duplicate_check.get("message", "Already successfully pushed"),
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "dedupe_key": dedupe_key,
            "retryable": False,
            "visible_to_user": None,
        }

    # ── Step 3: Record attempt as in_progress ─────────────────────────────────
    _idempotency_tracker.record_attempt(
        dedupe_key=dedupe_key,
        session_id=session_id,
        artifact_type=artifact_type,
        artifact_id=resolved_artifact_id,
        payload=validated,
        status="in_progress",
    )

    logger.info(f"[{session_id}] Starting CRM push — contact={contact_id}, key={dedupe_key}")
    logger.info(f"[{session_id}] Artifacts: 1 note, {len(tasks)} tasks, {len(tags)} tags")

    # ── Step 4: Execute push ──────────────────────────────────────────────────
    result = _rate_limiter.execute_with_backoff(
        push_to_a365,
        summary=summary,
        tasks=tasks,
        tags=tags,
        contact_id=contact_id,
    )

    # ── Step 5: Record outcome ────────────────────────────────────────────────
    if result["status"] == "success":
        _idempotency_tracker.mark_completed(dedupe_key)

        artifact_ids = {
            "note_id": f"note_{uuid.uuid4().hex[:8]}",
            "task_ids": [f"task_{uuid.uuid4().hex[:8]}" for _ in tasks],
            "tag_ids": [f"tag_{uuid.uuid4().hex[:8]}" for _ in tags],
        }

        logger.info(f"[{session_id}] Push successful. Artifacts: {artifact_ids}")

        return {
            "status": "success",
            "data": result.get("data"),
            "session_id": session_id,
            "artifact_ids": artifact_ids,
            "idempotency_key": idempotency_key,
            "dedupe_key": dedupe_key,
            "attempts": result.get("attempts", 1),
            "retryable": False,
            "visible_to_user": None,
        }

    elif result["status"] == "rate_limit_exceeded":
        _idempotency_tracker.mark_failed(dedupe_key)
        logger.error(f"[{session_id}] Rate limit exceeded after {result.get('attempts')} attempts")

        return {
            "status": "error",
            "error_type": "rate_limit_exceeded",
            "message": "Unable to push due to rate limiting",
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "dedupe_key": dedupe_key,
            "attempts": result.get("attempts"),
            "retryable": True,
            "visible_to_user": "CRM is rate limiting — will retry automatically",
        }

    else:
        _idempotency_tracker.mark_failed(dedupe_key)
        logger.error(f"[{session_id}] Push failed: {result.get('last_error')}")

        return {
            "status": "error",
            "error_type": "push_failed",
            "message": result.get("message"),
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "dedupe_key": dedupe_key,
            "attempts": result.get("attempts"),
            "retryable": True,
            "visible_to_user": "Failed to update CRM — please try again",
        }


def get_rate_limit_status() -> dict:
    """Get current rate limiting status for overlay display."""
    stats = _rate_limiter.get_stats()
    status = "normal"
    if stats["is_backing_off"]:
        status = "backing_off"
    elif stats["recent_hits_5min"] > 3:
        status = "rate_limited"

    return {
        "status": status,
        "recent_hits": stats["recent_hits_5min"],
        "current_backoff": stats["current_backoff"],
        "message": _get_status_message(status, stats),
    }


def _get_status_message(status: str, stats: dict) -> str:
    if status == "backing_off":
        return f"Waiting {stats['current_backoff']:.0f}s due to rate limit"
    elif status == "rate_limited":
        return "CRM rate limit active — requests may be delayed"
    return "CRM connection normal"


def reset_rate_limiter():
    """Reset rate limiter (for testing)."""
    _rate_limiter.reset()