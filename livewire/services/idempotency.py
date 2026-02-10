"""
WS5-2.3 — Idempotency + Validation Layer

Purpose:
- Prevent duplicate CRM writes
- Survive retries, reconnects, repeated pushes
- Provide clean, predictable behavior for demo
"""

import hashlib
import json
import logging
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# -------------------------
# In-memory dedupe store
# -------------------------
# key -> timestamp
_DEDUPE_STORE: Dict[str, datetime] = {}

# How long to remember writes (demo-safe)
DEDUP_TTL_MINUTES = 60


# -------------------------
# Validation
# -------------------------
REQUIRED_FIELDS = {
    "session_id": str,
    "artifact_type": str,   # e.g. "call_summary", "tasks", "tags"
    "payload": dict
}


class ValidationError(Exception):
    pass


def validate_payload(data: Dict[str, Any]) -> None:
    """Validate required fields and types"""
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
        if not isinstance(data[field], field_type):
            raise ValidationError(
                f"Invalid type for '{field}', expected {field_type.__name__}"
            )


# -------------------------
# Idempotency helpers
# -------------------------
def _stable_hash(payload: Dict[str, Any]) -> str:
    """
    Create a deterministic hash of payload content
    """
    normalized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _dedupe_key(session_id: str, artifact_type: str, payload_hash: str) -> str:
    return f"{session_id}:{artifact_type}:{payload_hash}"


def _cleanup_expired_entries():
    """Remove expired dedupe entries"""
    now = datetime.utcnow()
    expired = [
        key for key, ts in _DEDUPE_STORE.items()
        if now - ts > timedelta(minutes=DEDUP_TTL_MINUTES)
    ]
    for key in expired:
        del _DEDUPE_STORE[key]


# -------------------------
# Public API
# -------------------------
def check_and_mark_idempotent(
    session_id: str,
    artifact_type: str,
    payload: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Returns:
        (is_duplicate, dedupe_key)
    """
    _cleanup_expired_entries()

    payload_hash = _stable_hash(payload)
    key = _dedupe_key(session_id, artifact_type, payload_hash)

    if key in _DEDUPE_STORE:
        logger.info(f"[IDEMPOTENCY] Duplicate detected: {key}")
        return True, key

    _DEDUPE_STORE[key] = datetime.utcnow()
    logger.info(f"[IDEMPOTENCY] Recorded new write: {key}")
    return False, key


def reset_dedupe_store():
    """Testing / debug helper"""
    _DEDUPE_STORE.clear()
    logger.info("[IDEMPOTENCY] Store reset")


def get_dedupe_stats() -> Dict[str, Any]:
    return {
        "entries": len(_DEDUPE_STORE)
    }
