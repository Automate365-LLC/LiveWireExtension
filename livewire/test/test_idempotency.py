from livewire.services.idempotency import (
    check_and_mark_idempotent,
    reset_dedupe_store,
    validate_payload,
    ValidationError
)


def setup_function():
    reset_dedupe_store()


def test_duplicate_detection():
    payload = {"a": 1}

    first, _ = check_and_mark_idempotent("s1", "summary", payload)
    second, _ = check_and_mark_idempotent("s1", "summary", payload)

    assert first is False
    assert second is True


def test_different_payload_not_duplicate():
    p1 = {"a": 1}
    p2 = {"a": 2}

    assert check_and_mark_idempotent("s1", "summary", p1)[0] is False
    assert check_and_mark_idempotent("s1", "summary", p2)[0] is False


def test_validation_missing_field():
    try:
        validate_payload({
            "session_id": "s1",
            "artifact_type": "summary"
        })
        assert False
    except ValidationError:
        assert True

