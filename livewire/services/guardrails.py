from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)

class GuardrailEngine:
    def __init__(self):
        self.last_card_time = None
        self.recent_objections = deque(maxlen=10)
        self.objection_timestamps = deque(maxlen=10)
        self.DEBOUNCE_SECONDS = 30
        self.MAX_CARDS_PER_5MIN = 3
        
    def should_show_card(self, objection_type: str) -> bool:
        now = datetime.now()
        
        if self.last_card_time:
            time_since_last = (now - self.last_card_time).total_seconds()
            if time_since_last < self.DEBOUNCE_SECONDS:
                logger.info(f"Card blocked: debounce ({time_since_last:.1f}s < {self.DEBOUNCE_SECONDS}s)")
                return False
        
        if self.recent_objections and self.recent_objections[-1] == objection_type:
            logger.info(f"Card blocked: duplicate objection type '{objection_type}'")
            return False
        
        five_min_ago = now - timedelta(minutes=5)
        recent_count = sum(1 for ts in self.objection_timestamps if ts > five_min_ago)
        if recent_count >= self.MAX_CARDS_PER_5MIN:
            logger.info(f"Card blocked: rate limit ({recent_count}/{self.MAX_CARDS_PER_5MIN} in 5min)")
            return False
        
        self.last_card_time = now
        self.recent_objections.append(objection_type)
        self.objection_timestamps.append(now)
        logger.info(f"Card allowed: '{objection_type}'")
        return True
    
    def reset(self):
        self.last_card_time = None
        self.recent_objections.clear()
        self.objection_timestamps.clear()
        logger.info("Guardrails reset")
    
    def get_stats(self) -> dict:
        now = datetime.now()
        five_min_ago = now - timedelta(minutes=5)
        recent_count = sum(1 for ts in self.objection_timestamps if ts > five_min_ago)
        
        return {
            "cards_shown_last_5min": recent_count,
            "last_card_time": self.last_card_time.isoformat() if self.last_card_time else None,
            "recent_objections": list(self.recent_objections)
        }