"""
WS5-2.4 Tests: Rate Limit Handling
Tests verify backoff works and system recovers
"""

import pytest
import time
from services.rate_limit_handler import RateLimitHandler, mock_ghl_api_call


class TestRateLimitHandler:
    
    def setup_method(self):
        self.handler = RateLimitHandler(max_retries=5, base_delay=0.1)
    
    def test_successful_call_no_retry(self):
        result = self.handler.execute_with_backoff(
            mock_ghl_api_call,
            {"note": "Test"},
            fail_mode=None
        )
        
        assert result["status"] == "success"
        assert result["attempts"] == 1
    
    def test_rate_limit_triggers_backoff(self):
        """DoD: Simulated rate limit triggers backoff"""
        call_count = [0]
        
        def rate_limit_twice_then_success(payload, fail_mode=None):
            call_count[0] += 1
            if call_count[0] <= 2:
                return mock_ghl_api_call(payload, "rate_limit")
            return mock_ghl_api_call(payload, None)
        
        start_time = time.time()
        result = self.handler.execute_with_backoff(
            rate_limit_twice_then_success,
            {"note": "Test"}
        )
        elapsed = time.time() - start_time
        
        assert result["status"] == "success"
        assert result["attempts"] == 3
        assert elapsed > 0.3
        
        stats = self.handler.get_stats()
        assert stats["total_rate_limit_hits"] >= 2
    
    def test_system_recovers_after_rate_limit(self):
        """DoD: System recovers after rate limit"""
        call_count = [0]
        
        def rate_limit_then_success(payload, fail_mode=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_ghl_api_call(payload, "rate_limit")
            return mock_ghl_api_call(payload, None)
        
        result = self.handler.execute_with_backoff(
            rate_limit_then_success,
            {"note": "Test"}
        )
        
        assert result["status"] == "success"
        assert call_count[0] == 2
    
    def test_max_retries_exhausted(self):
        result = self.handler.execute_with_backoff(
            mock_ghl_api_call,
            {"note": "Test"},
            fail_mode="rate_limit"
        )
        
        assert result["status"] == "rate_limit_exceeded"
        assert result["attempts"] == self.handler.max_retries
    
    def test_exponential_backoff_timing(self):
        call_count = [0]
        call_times = []
        
        def always_rate_limit(payload, fail_mode=None):
            call_count[0] += 1
            call_times.append(time.time())
            return mock_ghl_api_call(payload, "rate_limit")
        
        self.handler.execute_with_backoff(
            always_rate_limit,
            {"note": "Test"}
        )
        
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]
            assert delay2 > delay1
    
    def test_no_task_storm(self):
        """DoD: No task storms - max retries limit prevents infinite retries"""
        call_count = [0]
        
        def always_fail(payload, fail_mode=None):
            call_count[0] += 1
            return mock_ghl_api_call(payload, "rate_limit")
        
        result = self.handler.execute_with_backoff(
            always_fail,
            {"note": "Test"}
        )
        
        assert call_count[0] == self.handler.max_retries
        assert call_count[0] <= 10
    
    def test_stats_tracking(self):
        self.handler.execute_with_backoff(
            mock_ghl_api_call,
            {"note": "Test"},
            fail_mode="rate_limit"
        )
        
        stats = self.handler.get_stats()
        assert stats["total_rate_limit_hits"] > 0
        assert stats["last_rate_limit"] is not None
    
    def test_reset_clears_state(self):
        self.handler.execute_with_backoff(
            mock_ghl_api_call,
            {"note": "Test"},
            fail_mode="rate_limit"
        )
        
        self.handler.reset()
        stats = self.handler.get_stats()
        
        assert stats["total_rate_limit_hits"] == 0
        assert stats["last_rate_limit"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])