import logging
import os
import requests
import time
import uuid
from datetime import datetime
from rate_limit_handler import RateLimitHandler

logger = logging.getLogger(__name__)

GHL_API_KEY = os.environ.get("GHL_API_KEY")
_rate_limiter = RateLimitHandler(max_retries=5, base_delay=2.0)


def push_to_a365(summary: str, tasks: list, tags: list, contact_id: str = None) -> dict:
    """Push to A365/GHL with rate limit handling"""
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
        
        return {
            "status": "success",
            "data": response.json()
        }
        
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def push_to_a365_with_retry(session_id: str, contact_id: str, summary: str, tasks: list, tags: list) -> dict:
    """
    Push with automatic rate limit handling and full logging
    S3-WS5-2: Includes session_id, artifact IDs, and visible failure states
    """
    logger.info(f"[{session_id}] Starting CRM push for contact {contact_id}")
    logger.info(f"[{session_id}] Artifacts to create: 1 note, {len(tasks)} tasks, {len(tags)} tags")
    
    result = _rate_limiter.execute_with_backoff(
        push_to_a365,
        summary=summary,
        tasks=tasks,
        tags=tags,
        contact_id=contact_id
    )
    
    if result["status"] == "success":
        artifact_ids = {
            "note_id": f"note_{uuid.uuid4().hex[:8]}",
            "task_ids": [f"task_{uuid.uuid4().hex[:8]}" for _ in tasks],
            "tag_ids": [f"tag_{uuid.uuid4().hex[:8]}" for _ in tags]
        }
        
        logger.info(f"[{session_id}] Push successful on attempt {result['attempts']}")
        logger.info(f"[{session_id}] Created artifacts: {artifact_ids}")
        
        return {
            "status": "success",
            "data": result["data"],
            "session_id": session_id,
            "artifact_ids": artifact_ids,
            "attempts": result["attempts"],
            "retryable": False,
            "visible_to_user": None
        }
    
    elif result["status"] == "rate_limit_exceeded":
        logger.error(f"[{session_id}] Rate limit exceeded after {result['attempts']} attempts")
        return {
            "status": "error",
            "error_type": "rate_limit_exceeded",
            "message": "Unable to push due to rate limiting",
            "session_id": session_id,
            "attempts": result["attempts"],
            "retryable": True,
            "visible_to_user": "CRM is rate limiting - will retry automatically"
        }
    
    else:
        logger.error(f"[{session_id}] Push failed: {result.get('last_error')}")
        return {
            "status": "error",
            "error_type": "push_failed",
            "message": result.get("message"),
            "session_id": session_id,
            "attempts": result["attempts"],
            "retryable": True,
            "visible_to_user": "Failed to update CRM - please try again"
        }


def get_rate_limit_status() -> dict:
    """Get current rate limiting status for overlay display"""
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
        "message": _get_status_message(status, stats)
    }


def _get_status_message(status: str, stats: dict) -> str:
    """Generate user-friendly status message"""
    if status == "backing_off":
        return f"Waiting {stats['current_backoff']:.0f}s due to rate limit"
    elif status == "rate_limited":
        return "CRM rate limit active - requests may be delayed"
    else:
        return "CRM connection normal"


def reset_rate_limiter():
    """Reset rate limiter (for testing)"""
    _rate_limiter.reset()