import pytest
from livewire.services.a365_integration import push_to_a365


def extract_payload(result):
    assert result["status"] == "success"
    assert "payload" in result
    return result["payload"]


def test_push_basic():
    result = push_to_a365(
        summary="Customer mentioned budget concerns",
        tasks=["Follow up with pricing options"],
        tags=["pricing_objection"]
    )
    payload = extract_payload(result)
    assert payload["note"] == "Customer mentioned budget concerns"
    assert len(payload["action_items"]) == 1
    assert payload["categories"] == ["pricing_objection"]


def test_push_empty_tasks():
    result = push_to_a365(
        summary="Test",
        tasks=[],
        tags=["test"]
    )
    payload = extract_payload(result)
    assert payload["action_items"] == []
    assert payload["note"] == "Test"


def test_push_empty_tags():
    result = push_to_a365(
        summary="Test",
        tasks=["Task 1"],
        tags=[]
    )
    payload = extract_payload(result)
    assert payload["categories"] == []


def test_push_long_summary():
    long_text = "A" * 1000
    result = push_to_a365(
        summary=long_text,
        tasks=[],
        tags=[]
    )
    payload = extract_payload(result)
    assert len(payload["note"]) == 1000


def test_push_special_characters():
    result = push_to_a365(
        summary="Test with special chars: @#$%^&*()",
        tasks=["Task with 'quotes'"],
        tags=["tag-with-dash"]
    )
    payload = extract_payload(result)
    assert "@#$%^&*()" in payload["note"]


def test_push_timestamp_exists():
    result = push_to_a365("Test", [], [])
    payload = extract_payload(result)
    assert "timestamp" in payload
    assert payload["timestamp"] is not None


def test_push_source_field():
    result = push_to_a365("Test", [], [])
    payload = extract_payload(result)
    assert payload["source"] == "livewire"


def test_push_multiple_tasks():
    tasks = ["Task 1", "Task 2", "Task 3"]
    result = push_to_a365("Summary", tasks, [])
    payload = extract_payload(result)
    assert len(payload["action_items"]) == 3


def test_push_multiple_tags():
    tags = ["tag1", "tag2", "tag3"]
    result = push_to_a365("Summary", [], tags)
    payload = extract_payload(result)
    assert len(payload["categories"]) == 3
