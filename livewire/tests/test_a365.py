import pytest
from services.a365_integration import push_to_a365, push_to_a365_retry

def test_push_basic():
    result = push_to_a365(
        summary="Customer mentioned budget concerns",
        tasks=["Follow up with pricing options"],
        tags=["pricing_objection"]
    )
    assert result["note"] == "Customer mentioned budget concerns"
    assert len(result["action_items"]) == 1
    assert result["categories"] == ["pricing_objection"]

def test_push_empty_tasks():
    result = push_to_a365(
        summary="Test",
        tasks=[],
        tags=["test"]
    )
    assert result["action_items"] == []
    assert result["note"] == "Test"

def test_push_empty_tags():
    result = push_to_a365(
        summary="Test",
        tasks=["Task 1"],
        tags=[]
    )
    assert result["categories"] == []

def test_push_long_summary():
    long_text = "A" * 1000
    result = push_to_a365(
        summary=long_text,
        tasks=[],
        tags=[]
    )
    assert len(result["note"]) == 1000

def test_push_special_characters():
    result = push_to_a365(
        summary="Test with special chars: @#$%^&*()",
        tasks=["Task with 'quotes'"],
        tags=["tag-with-dash"]
    )
    assert "@#$%^&*()" in result["note"]

def test_push_timestamp_exists():
    result = push_to_a365("Test", [], [])
    assert "timestamp" in result
    assert result["timestamp"] is not None

def test_push_source_field():
    result = push_to_a365("Test", [], [])
    assert result["source"] == "livewire"

def test_push_multiple_tasks():
    tasks = ["Task 1", "Task 2", "Task 3"]
    result = push_to_a365("Summary", tasks, [])
    assert len(result["action_items"]) == 3

def test_push_multiple_tags():
    tags = ["tag1", "tag2", "tag3"]
    result = push_to_a365("Summary", [], tags)
    assert len(result["categories"]) == 3