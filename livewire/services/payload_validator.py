"""
P1-WS5.3 — Payload Validator
Validates CRM push payloads before idempotency check and push execution.
Owner: Nishitha
"""

import re
import hashlib
import json
from typing import Optional


# ── Required fields spec ────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "session_id": {
        "type": str,
        "description": "Unique identifier for the call/session",
        "example": "session_abc123",
    },
    "artifact_type": {
        "type": str,
        "allowed_values": ["note", "task", "tag", "full_push"],
        "description": "What kind of CRM artifact this payload represents",
        "example": "full_push",
    },
    "contact_id": {
        "type": str,
        "description": "GHL contact ID to write artifacts against",
        "example": "contact_xyz789",
    },
    "summary": {
        "type": str,
        "min_length": 1,
        "max_length": 5000,
        "description": "Call summary note text",
        "example": "Customer expressed price concerns...",
    },
    "tasks": {
        "type": list,
        "description": "List of action item strings",
        "example": ["Send pricing deck", "Schedule follow-up"],
    },
    "tags": {
        "type": list,
        "description": "List of CRM tag strings",
        "example": ["objection_price", "LiveWire Demo"],
    },
}

OPTIONAL_FIELDS = {
    "artifact_id": {
        "type": str,
        "description": "Caller-supplied stable ID for this artifact (used in dedupe key). "
                       "If omitted, one is derived from session_id + artifact_type.",
    },
    "seq": {
        "type": int,
        "description": "Monotonic sequence number from the session event stream",
    },
    "schema_version": {
        "type": str,
        "description": "LiveWire schema version (e.g. '0.1')",
    },
}


# ── Validator ────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when payload fails validation."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Payload validation failed: {'; '.join(errors)}")


def validate_payload(payload: dict) -> dict:
    """
    Validate a CRM push payload against the required fields spec.

    Returns the validated payload (with defaults applied) on success.
    Raises ValidationError listing all problems if anything is wrong.

    Usage:
        try:
            clean = validate_payload(raw)
        except ValidationError as e:
            print(e.errors)
    """
    if not isinstance(payload, dict):
        raise ValidationError(["payload must be a dict, got: " + type(payload).__name__])

    errors: list[str] = []

    # ── 1. Required field presence and type checks ──────────────────────────
    for field, spec in REQUIRED_FIELDS.items():
        if field not in payload:
            errors.append(f"Missing required field: '{field}'")
            continue

        value = payload[field]

        if not isinstance(value, spec["type"]):
            errors.append(
                f"'{field}' must be {spec['type'].__name__}, "
                f"got {type(value).__name__}"
            )
            continue

        # String-specific checks
        if spec["type"] is str:
            if not value.strip():
                errors.append(f"'{field}' must not be empty or whitespace-only")
            if "min_length" in spec and len(value) < spec["min_length"]:
                errors.append(f"'{field}' too short (min {spec['min_length']} chars)")
            if "max_length" in spec and len(value) > spec["max_length"]:
                errors.append(
                    f"'{field}' too long ({len(value)} chars, max {spec['max_length']})"
                )
            if "allowed_values" in spec and value not in spec["allowed_values"]:
                errors.append(
                    f"'{field}' must be one of {spec['allowed_values']}, got '{value}'"
                )

        # List-specific checks
        if spec["type"] is list:
            if not isinstance(value, list):
                errors.append(f"'{field}' must be a list")
            else:
                for i, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(
                            f"'{field}[{i}]' must be a string, got {type(item).__name__}"
                        )

    # ── 2. Optional field type checks (only if present) ─────────────────────
    for field, spec in OPTIONAL_FIELDS.items():
        if field in payload:
            value = payload[field]
            if not isinstance(value, spec["type"]):
                errors.append(
                    f"Optional field '{field}' must be {spec['type'].__name__}, "
                    f"got {type(value).__name__}"
                )

    # ── 3. Cross-field sanity checks ─────────────────────────────────────────
    # session_id format: non-trivial (at least 4 chars, no spaces)
    if "session_id" in payload and isinstance(payload["session_id"], str):
        sid = payload["session_id"]
        if len(sid) < 4:
            errors.append("'session_id' must be at least 4 characters")
        if " " in sid:
            errors.append("'session_id' must not contain spaces")

    # contact_id must not be blank
    if "contact_id" in payload and isinstance(payload["contact_id"], str):
        if not payload["contact_id"].strip():
            errors.append("'contact_id' must not be blank")

    if errors:
        raise ValidationError(errors)

    # ── 4. Apply defaults for optional fields ────────────────────────────────
    validated = dict(payload)
    if "schema_version" not in validated:
        validated["schema_version"] = "0.1"
    if "artifact_id" not in validated:
        # Derive a stable artifact_id from session + type so callers don't have to supply it
        validated["artifact_id"] = _derive_artifact_id(
            validated["session_id"], validated["artifact_type"]
        )

    return validated


def _derive_artifact_id(session_id: str, artifact_type: str) -> str:
    """Derive a stable artifact_id when the caller hasn't supplied one."""
    raw = f"{session_id}:{artifact_type}"
    return "art_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


# ── Idempotency key generation ────────────────────────────────────────────────

def generate_idempotency_key(session_id: str, artifact_type: str, payload: dict) -> str:
    """
    Build the idempotency key per the P1-WS5.3 spec:

        key = session_id + artifact_type + sha256(payload)

    The payload hash covers the *content* so that a changed payload
    is treated as a new push (not a duplicate).
    """
    payload_hash = _hash_payload(payload)
    raw_key = f"{session_id}:{artifact_type}:{payload_hash}"
    # Return a compact fixed-length key for the DB
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _hash_payload(payload: dict) -> str:
    """Stable SHA-256 hash of a dict payload."""
    # Exclude fields that change on every call (timestamp) so hash is stable
    hashable = {k: v for k, v in payload.items() if k not in ("timestamp", "schema_version")}
    payload_str = json.dumps(hashable, sort_keys=True)
    return hashlib.sha256(payload_str.encode()).hexdigest()


# ── Human-readable field reference ───────────────────────────────────────────

def describe_required_fields() -> str:
    """Return a formatted string listing all required and optional fields."""
    lines = ["=== Required Fields ==="]
    for field, spec in REQUIRED_FIELDS.items():
        lines.append(f"  {field} ({spec['type'].__name__}): {spec['description']}")
        lines.append(f"    example: {spec['example']}")
    lines.append("\n=== Optional Fields ===")
    for field, spec in OPTIONAL_FIELDS.items():
        lines.append(f"  {field} ({spec['type'].__name__}): {spec['description']}")
    return "\n".join(lines)