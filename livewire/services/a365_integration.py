"""
A365/GHL Integration with Rate Limiting
Handles CRM pushes with exponential backoff on rate limits
"""

from datetime import datetime
import logging
import os
import requests
from services.rate_limit_handler import RateLimitHandler, mock_ghl_api_call

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


def push_to_a365_with_retry(
    summary: str,
    tasks: list,
    tags: list,
    contact_id: str
) -> dict:
    """
    Push with automatic rate limit handling and exponential backoff
    Use this for all production pushes
    """
    logger.info(f"Pushing to A365 for contact={contact_id}")
    
    result = _rate_limiter.execute_with_backoff(
        push_to_a365,
        summary=summary,
        tasks=tasks,
        tags=tags,
        contact_id=contact_id
    )
    
    if result["status"] == "rate_limit_exceeded":
        logger.error(f"Rate limit exceeded after {result['attempts']} attempts")
        return {
            "status": "error",
            "error_type": "rate_limit_exceeded",
            "message": "Unable to push due to rate limiting",
            "attempts": result["attempts"],
            "overlay_message": "CRM is rate limiting - will retry automatically"
        }
    
    if result["status"] == "error":
        logger.error(f"Push failed: {result.get('last_error')}")
        return {
            "status": "error",
            "error_type": "push_failed",
            "message": result.get("message"),
            "attempts": result["attempts"],
            "overlay_message": "Failed to update CRM - please try again"
        }
    
    logger.info(f"Push successful on attempt {result['attempts']}")
    return {
        "status": "success",
        "data": result["data"],
        "attempts": result["attempts"],
        "message": f"Successfully pushed after {result['attempts']} attempt(s)"
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