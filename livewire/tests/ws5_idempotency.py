"""
P1-WS5.3 — Idempotency + Validation Test Suite
Owner: Nishitha

Covers:
  - Required field validation (catches malformed payloads)
  - Idempotency key generation (stable, deterministic)
  - Duplicate prevention (repeat send → zero duplicates)
  - Partial failure + retry behavior
  - Payload hash change → new push allowed
"""

import os
import tempfile
import pytest
import sys

# Allow running from the tests/ folder with services/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))

from payload_validator import (
    validate_payload,
    generate_idempotency_key,
    ValidationError,
    describe_required_fields,
)
from idempotency_tracker import IdempotencyTracker


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_payload():
    """A minimal, fully valid CRM push payload."""
    return {
        "session_id": "sess_test_001",
        "artifact_type": "full_push",
        "contact_id": "contact_abc123",
        "summary": "Customer raised pricing concerns during demo.",
        "tasks": ["Send updated pricing deck", "Schedule follow-up call"],
        "tags": ["objection_price", "LiveWire Demo"],
    }


@pytest.fixture
def tracker(tmp_path):
    """Fresh IdempotencyTracker backed by a temp DB for each test."""
    db_file = str(tmp_path / "test_idempotency.db")
    return IdempotencyTracker(db_path=db_file)


# ══════════════════════════════════════════════════════════════════════════════
# 1. PAYLOAD VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestPayloadValidation:

    def test_valid_payload_passes(self, valid_payload):
        """A well-formed payload should pass without errors."""
        result = validate_payload(valid_payload)
        assert result["session_id"] == valid_payload["session_id"]
        assert result["artifact_type"] == valid_payload["artifact_type"]

    def test_missing_session_id_raises(self, valid_payload):
        del valid_payload["session_id"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("session_id" in e for e in exc.value.errors)

    def test_missing_contact_id_raises(self, valid_payload):
        del valid_payload["contact_id"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("contact_id" in e for e in exc.value.errors)

    def test_missing_summary_raises(self, valid_payload):
        del valid_payload["summary"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("summary" in e for e in exc.value.errors)

    def test_missing_tasks_raises(self, valid_payload):
        del valid_payload["tasks"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("tasks" in e for e in exc.value.errors)

    def test_missing_tags_raises(self, valid_payload):
        del valid_payload["tags"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("tags" in e for e in exc.value.errors)

    def test_missing_artifact_type_raises(self, valid_payload):
        del valid_payload["artifact_type"]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("artifact_type" in e for e in exc.value.errors)

    def test_invalid_artifact_type_raises(self, valid_payload):
        valid_payload["artifact_type"] = "banana"
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("artifact_type" in e for e in exc.value.errors)

    def test_all_valid_artifact_types_accepted(self, valid_payload):
        for atype in ["note", "task", "tag", "full_push"]:
            valid_payload["artifact_type"] = atype
            result = validate_payload(valid_payload)
            assert result["artifact_type"] == atype

    def test_empty_summary_raises(self, valid_payload):
        valid_payload["summary"] = "   "
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("summary" in e for e in exc.value.errors)

    def test_summary_too_long_raises(self, valid_payload):
        valid_payload["summary"] = "X" * 5001
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("summary" in e for e in exc.value.errors)

    def test_tasks_must_be_list(self, valid_payload):
        valid_payload["tasks"] = "not a list"
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("tasks" in e for e in exc.value.errors)

    def test_tasks_items_must_be_strings(self, valid_payload):
        valid_payload["tasks"] = ["valid task", 42, None]
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("tasks" in e for e in exc.value.errors)

    def test_empty_tasks_allowed(self, valid_payload):
        """Empty task list is valid (some calls have no follow-ups)."""
        valid_payload["tasks"] = []
        result = validate_payload(valid_payload)
        assert result["tasks"] == []

    def test_empty_tags_allowed(self, valid_payload):
        valid_payload["tags"] = []
        result = validate_payload(valid_payload)
        assert result["tags"] == []

    def test_short_session_id_raises(self, valid_payload):
        valid_payload["session_id"] = "ab"
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("session_id" in e for e in exc.value.errors)

    def test_session_id_with_spaces_raises(self, valid_payload):
        valid_payload["session_id"] = "sess 001"
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("session_id" in e for e in exc.value.errors)

    def test_blank_contact_id_raises(self, valid_payload):
        valid_payload["contact_id"] = "   "
        with pytest.raises(ValidationError) as exc:
            validate_payload(valid_payload)
        assert any("contact_id" in e for e in exc.value.errors)

    def test_multiple_missing_fields_all_reported(self):
        """All missing fields should appear in a single ValidationError."""
        with pytest.raises(ValidationError) as exc:
            validate_payload({})
        assert len(exc.value.errors) >= len(["session_id", "artifact_type",
                                              "contact_id", "summary", "tasks", "tags"])

    def test_schema_version_default_applied(self, valid_payload):
        """schema_version should default to '0.1' when not supplied."""
        result = validate_payload(valid_payload)
        assert result["schema_version"] == "0.1"

    def test_artifact_id_derived_when_missing(self, valid_payload):
        """artifact_id should be auto-derived when omitted."""
        result = validate_payload(valid_payload)
        assert "artifact_id" in result
        assert result["artifact_id"].startswith("art_")

    def test_artifact_id_preserved_when_supplied(self, valid_payload):
        valid_payload["artifact_id"] = "my_custom_id"
        result = validate_payload(valid_payload)
        assert result["artifact_id"] == "my_custom_id"

    def test_describe_required_fields_returns_string(self):
        doc = describe_required_fields()
        assert isinstance(doc, str)
        assert "session_id" in doc
        assert "contact_id" in doc


# ══════════════════════════════════════════════════════════════════════════════
# 2. IDEMPOTENCY KEY GENERATION
# ══════════════════════════════════════════════════════════════════════════════

class TestIdempotencyKeyGeneration:

    def test_key_is_deterministic(self, valid_payload):
        """Same inputs must always produce the same key."""
        k1 = generate_idempotency_key("sess_001", "full_push", valid_payload)
        k2 = generate_idempotency_key("sess_001", "full_push", valid_payload)
        assert k1 == k2

    def test_different_session_ids_produce_different_keys(self, valid_payload):
        k1 = generate_idempotency_key("sess_001", "full_push", valid_payload)
        k2 = generate_idempotency_key("sess_002", "full_push", valid_payload)
        assert k1 != k2

    def test_different_artifact_types_produce_different_keys(self, valid_payload):
        k1 = generate_idempotency_key("sess_001", "note", valid_payload)
        k2 = generate_idempotency_key("sess_001", "task", valid_payload)
        assert k1 != k2

    def test_changed_payload_produces_different_key(self, valid_payload):
        k1 = generate_idempotency_key("sess_001", "full_push", valid_payload)
        changed = dict(valid_payload)
        changed["summary"] = "A completely different summary"
        k2 = generate_idempotency_key("sess_001", "full_push", changed)
        assert k1 != k2

    def test_key_is_fixed_length_hex(self, valid_payload):
        key = generate_idempotency_key("sess_001", "full_push", valid_payload)
        assert len(key) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

    def test_timestamp_excluded_from_hash(self, valid_payload):
        """Adding/changing timestamp should NOT change the idempotency key."""
        p1 = dict(valid_payload)
        p2 = dict(valid_payload)
        p2["timestamp"] = "2099-01-01T00:00:00"
        k1 = generate_idempotency_key("sess_001", "full_push", p1)
        k2 = generate_idempotency_key("sess_001", "full_push", p2)
        assert k1 == k2


# ══════════════════════════════════════════════════════════════════════════════
# 3. DUPLICATE PREVENTION — REPEAT SEND
# ══════════════════════════════════════════════════════════════════════════════

class TestDuplicatePrevention:

    def test_first_push_not_a_duplicate(self, tracker, valid_payload):
        """A brand-new key should not be flagged as a duplicate."""
        dedupe_key = tracker.generate_dedupe_key("sess_001", "full_push", "art_aaa")
        result = tracker.check_duplicate(dedupe_key, valid_payload)
        assert result is None

    def test_completed_push_detected_as_duplicate(self, tracker, valid_payload):
        """After marking completed, the same key must be caught as a duplicate."""
        dedupe_key = tracker.generate_dedupe_key("sess_001", "full_push", "art_aaa")

        # Simulate a successful first push
        tracker.record_attempt(dedupe_key, "sess_001", "full_push", "art_aaa", valid_payload)
        tracker.mark_completed(dedupe_key)

        # Second call should be blocked
        result = tracker.check_duplicate(dedupe_key, valid_payload)
        assert result is not None
        assert result["duplicate"] is True
        assert result["status"] == "completed"

    def test_repeat_send_twice_still_one_record(self, tracker, valid_payload):
        """Sending the exact same payload twice should result in only one DB record."""
        dedupe_key = tracker.generate_dedupe_key("sess_002", "full_push", "art_bbb")

        tracker.record_attempt(dedupe_key, "sess_002", "full_push", "art_bbb", valid_payload)
        tracker.mark_completed(dedupe_key)

        # Second attempt: check_duplicate should short-circuit before another record_attempt
        check = tracker.check_duplicate(dedupe_key, valid_payload)
        assert check["duplicate"] is True

        # Verify only one row in the DB
        import sqlite3
        conn = sqlite3.connect(tracker.db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM crm_pushes WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()[0]
        conn.close()
        assert rows == 1

    def test_different_sessions_are_independent(self, tracker, valid_payload):
        """Pushes for different session_ids must never block each other."""
        dk1 = tracker.generate_dedupe_key("sess_AAA", "full_push", "art_1")
        dk2 = tracker.generate_dedupe_key("sess_BBB", "full_push", "art_2")

        tracker.record_attempt(dk1, "sess_AAA", "full_push", "art_1", valid_payload)
        tracker.mark_completed(dk1)

        # sess_BBB's key should still be clear
        result = tracker.check_duplicate(dk2, valid_payload)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. PARTIAL FAILURE + RETRY
# ══════════════════════════════════════════════════════════════════════════════

class TestPartialFailureAndRetry:

    def test_failed_push_is_retryable(self, tracker, valid_payload):
        """A failed push should NOT block a retry (in_progress / failed → allow)."""
        dedupe_key = tracker.generate_dedupe_key("sess_003", "full_push", "art_ccc")

        tracker.record_attempt(dedupe_key, "sess_003", "full_push", "art_ccc", valid_payload)
        tracker.mark_failed(dedupe_key)

        # After failure, check_duplicate should allow a retry
        result = tracker.check_duplicate(dedupe_key, valid_payload)
        # mark_failed sets status='failed', which is not 'completed' → not a duplicate
        assert result is None or result.get("duplicate") is not True

    def test_in_progress_push_allows_retry(self, tracker, valid_payload):
        """An in_progress record (crashed mid-push) should not block a retry."""
        dedupe_key = tracker.generate_dedupe_key("sess_004", "full_push", "art_ddd")

        tracker.record_attempt(dedupe_key, "sess_004", "full_push", "art_ddd", valid_payload)
        # Do NOT call mark_completed — simulate a crash

        result = tracker.check_duplicate(dedupe_key, valid_payload)
        assert result is None or result.get("duplicate") is not True

    def test_attempts_counter_increments_on_retry(self, tracker, valid_payload):
        """Each retry should increment the attempts counter in the DB."""
        dedupe_key = tracker.generate_dedupe_key("sess_005", "full_push", "art_eee")

        tracker.record_attempt(dedupe_key, "sess_005", "full_push", "art_eee", valid_payload)
        tracker.mark_failed(dedupe_key)
        tracker.record_attempt(dedupe_key, "sess_005", "full_push", "art_eee", valid_payload)
        tracker.mark_failed(dedupe_key)
        tracker.record_attempt(dedupe_key, "sess_005", "full_push", "art_eee", valid_payload)
        tracker.mark_completed(dedupe_key)

        import sqlite3
        conn = sqlite3.connect(tracker.db_path)
        attempts = conn.execute(
            "SELECT attempts FROM crm_pushes WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()[0]
        conn.close()
        assert attempts == 3

    def test_changed_payload_on_retry_is_allowed(self, tracker, valid_payload):
        """If the payload changes (e.g. corrected summary), it should be treated as new."""
        dedupe_key = tracker.generate_dedupe_key("sess_006", "full_push", "art_fff")

        tracker.record_attempt(dedupe_key, "sess_006", "full_push", "art_fff", valid_payload)
        tracker.mark_completed(dedupe_key)

        changed_payload = dict(valid_payload)
        changed_payload["summary"] = "Updated summary after correction"

        result = tracker.check_duplicate(dedupe_key, changed_payload)
        # payload hash changed → not a duplicate
        assert result is None or result.get("duplicate") is not True

    def test_retry_after_partial_failure_succeeds(self, tracker, valid_payload):
        """Full happy-path retry flow: fail once, succeed on second attempt."""
        dedupe_key = tracker.generate_dedupe_key("sess_007", "full_push", "art_ggg")

        # First attempt — fails
        tracker.record_attempt(dedupe_key, "sess_007", "full_push", "art_ggg", valid_payload)
        tracker.mark_failed(dedupe_key)

        # Second attempt — check that retry is allowed then complete it
        check = tracker.check_duplicate(dedupe_key, valid_payload)
        assert check is None or check.get("duplicate") is not True

        tracker.record_attempt(dedupe_key, "sess_007", "full_push", "art_ggg", valid_payload)
        tracker.mark_completed(dedupe_key)

        # Third send — now it IS a duplicate
        final_check = tracker.check_duplicate(dedupe_key, valid_payload)
        assert final_check is not None
        assert final_check["duplicate"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. EDGE CASES
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_non_dict_payload_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_payload("not a dict")
        assert len(exc.value.errors) > 0

    def test_none_payload_raises(self):
        with pytest.raises(ValidationError):
            validate_payload(None)

    def test_validator_does_not_mutate_original(self, valid_payload):
        """validate_payload must not modify the caller's dict."""
        original_copy = dict(valid_payload)
        validate_payload(valid_payload)
        assert valid_payload == original_copy

    def test_cleanup_removes_old_records(self, tracker, valid_payload):
        """Records older than the cutoff should be purged."""
        import sqlite3
        from datetime import datetime, timedelta

        dedupe_key = tracker.generate_dedupe_key("sess_old", "full_push", "art_old")
        tracker.record_attempt(dedupe_key, "sess_old", "full_push", "art_old", valid_payload)
        tracker.mark_completed(dedupe_key)

        # Backdate the record to 40 days ago
        old_ts = (datetime.now() - timedelta(days=40)).isoformat()
        conn = sqlite3.connect(tracker.db_path)
        conn.execute(
            "UPDATE crm_pushes SET created_at = ? WHERE dedupe_key = ?",
            (old_ts, dedupe_key)
        )
        conn.commit()
        conn.close()

        tracker.cleanup_old_records(days=30)

        conn = sqlite3.connect(tracker.db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM crm_pushes WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()[0]
        conn.close()
        assert rows == 0

    def test_cleanup_preserves_recent_records(self, tracker, valid_payload):
        """Records within the cutoff must NOT be deleted."""
        dedupe_key = tracker.generate_dedupe_key("sess_new", "full_push", "art_new")
        tracker.record_attempt(dedupe_key, "sess_new", "full_push", "art_new", valid_payload)
        tracker.mark_completed(dedupe_key)

        tracker.cleanup_old_records(days=30)

        import sqlite3
        conn = sqlite3.connect(tracker.db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM crm_pushes WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()[0]
        conn.close()
        assert rows == 1


