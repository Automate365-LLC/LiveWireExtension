"""
WS5-2.4: Rate Limit Handler for GHL/A365
Handles API rate limits with exponential backoff
"""

import time
import logging
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class RateLimitHandler:
    """
    Handles GHL/A365 API rate limiting with exponential backoff
    Prevents task storms and surfaces errors appropriately
    """
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.rate_limit_hits = deque(maxlen=100)
        self.current_backoff = 0
        self.last_rate_limit_time = None
        
    def execute_with_backoff(self, 
                            func: Callable, 
                            *args, 
                            **kwargs) -> Dict:
        """
        Execute a function with exponential backoff on rate limit errors
        
        Returns:
            Result dict with status, data, and retry info
        """
        attempt = 0
        last_error = None
        
        while attempt < self.max_retries:
            try:
                result = func(*args, **kwargs)
                
                if self._is_rate_limited(result):
                    attempt += 1
                    delay = self._calculate_backoff(attempt)
                    
                    self._log_rate_limit(attempt, delay)
                    self.rate_limit_hits.append({
                        "timestamp": datetime.now(),
                        "attempt": attempt,
                        "delay": delay
                    })
                    
                    if attempt < self.max_retries:
                        logger.warning(f"Rate limited. Waiting {delay}s before retry {attempt + 1}/{self.max_retries}")
                        time.sleep(delay)
                        continue
                    else:
                        return {
                            "status": "rate_limit_exceeded",
                            "message": f"Rate limit hit after {self.max_retries} attempts",
                            "attempts": attempt,
                            "last_error": str(last_error)
                        }
                
                if self._is_error(result):
                    last_error = result.get("error", "Unknown error")
                    attempt += 1
                    
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff(attempt)
                        logger.warning(f"API error: {last_error}. Retrying in {delay}s")
                        time.sleep(delay)
                        continue
                    else:
                        return {
                            "status": "error",
                            "message": f"Failed after {self.max_retries} attempts",
                            "attempts": attempt,
                            "last_error": str(last_error)
                        }
                
                logger.info(f"Request successful on attempt {attempt + 1}")
                return {
                    "status": "success",
                    "data": result,
                    "attempts": attempt + 1
                }
                
            except Exception as e:
                last_error = e
                attempt += 1
                
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.error(f"Exception on attempt {attempt}: {e}. Retrying in {delay}s")
                    time.sleep(delay)
                else:
                    logger.error(f"All retries exhausted after exception: {e}")
                    return {
                        "status": "error",
                        "message": f"Exception after {self.max_retries} attempts: {str(e)}",
                        "attempts": attempt,
                        "last_error": str(e)
                    }
        
        return {
            "status": "error",
            "message": "Max retries reached",
            "attempts": attempt,
            "last_error": str(last_error)
        }
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.base_delay * (2 ** (attempt - 1))
        max_delay = 60.0
        return min(delay, max_delay)
    
    def _is_rate_limited(self, result: Dict) -> bool:
        """Check if response indicates rate limiting"""
        if isinstance(result, dict):
            if result.get("status_code") == 429:
                return True
            if result.get("error_type") == "rate_limit":
                return True
            if "rate limit" in str(result.get("error", "")).lower():
                return True
        return False
    
    def _is_error(self, result: Dict) -> bool:
        """Check if response is an error (but not rate limit)"""
        if isinstance(result, dict):
            if result.get("status") == "error":
                return True
            if result.get("error") and not self._is_rate_limited(result):
                return True
        return False
    
    def _log_rate_limit(self, attempt: int, delay: float):
        """Log rate limit hit"""
        self.last_rate_limit_time = datetime.now()
        self.current_backoff = delay
        
        logger.warning(
            f"Rate limit hit (attempt {attempt}/{self.max_retries}). "
            f"Backing off for {delay:.1f}s"
        )
    
    def get_stats(self) -> Dict:
        """Get rate limiting statistics"""
        recent_hits = [
            hit for hit in self.rate_limit_hits 
            if hit["timestamp"] > datetime.now() - timedelta(minutes=5)
        ]
        
        return {
            "total_rate_limit_hits": len(self.rate_limit_hits),
            "recent_hits_5min": len(recent_hits),
            "current_backoff": self.current_backoff,
            "last_rate_limit": self.last_rate_limit_time.isoformat() if self.last_rate_limit_time else None,
            "is_backing_off": self.current_backoff > 0
        }
    
    def reset(self):
        """Reset rate limit tracking"""
        self.rate_limit_hits.clear()
        self.current_backoff = 0
        self.last_rate_limit_time = None
        logger.info("Rate limit handler reset")


def mock_ghl_api_call(payload: Dict, fail_mode: str = None) -> Dict:
    """Mock GHL API call for testing rate limiting"""
    
    if fail_mode == "rate_limit":
        return {
            "status_code": 429,
            "error": "Rate limit exceeded",
            "error_type": "rate_limit"
        }
    
    if fail_mode == "error":
        return {
            "status": "error",
            "error": "API error occurred"
        }
    
    return {
        "status": "success",
        "data": payload,
        "crm_id": "mock_123"
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    handler = RateLimitHandler(max_retries=3, base_delay=0.5)
    
    print("\n=== Test 1: Normal success ===")
    result = handler.execute_with_backoff(
        mock_ghl_api_call,
        {"note": "Test note"},
        fail_mode=None
    )
    print(f"Result: {result['status']}")
    
    print("\n=== Test 2: Rate limit with recovery ===")
    call_count = [0]
    
    def rate_limit_then_success(payload, fail_mode=None):
        call_count[0] += 1
        if call_count[0] < 2:
            return mock_ghl_api_call(payload, "rate_limit")
        return mock_ghl_api_call(payload, None)
    
    result = handler.execute_with_backoff(
        rate_limit_then_success,
        {"note": "Test note"}
    )
    print(f"Result: {result['status']} after {result['attempts']} attempts")
    print(f"Stats: {handler.get_stats()}")