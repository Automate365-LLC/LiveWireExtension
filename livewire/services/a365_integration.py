from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def push_to_a365(summary: str, tasks: list, tags: list) -> dict:
    payload = {
        "note": summary,
        "action_items": tasks,
        "categories": tags,
        "timestamp": datetime.now().isoformat(),
        "source": "livewire"
    }
    
    logger.info(f"[MOCK] Would push to A365: {payload}")
    
    return payload

def push_to_a365_retry(summary: str, tasks: list, tags: list, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            return push_to_a365(summary, tasks, tags)
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
    return {}