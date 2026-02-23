import time
from collections import defaultdict, deque
from typing import Dict, List, Optional
from datetime import datetime, timedelta

class SuppressionEngine:
    def __init__(self):
        self.handled_cards: Dict[str, float] = {}
        self.cooldowns: Dict[str, float] = {}
        self.evidence_history: deque = deque(maxlen=100)
        
        self.COOLDOWN_WINDOWS = {
            "price": 300,
            "timing": 180,
            "features": 240,
            "competitor": 300,
            "authority": 180,
            "trust": 240,
            "default": 180
        }
        
        self.SUPPRESSION_WINDOW = 120
    
    def should_show_card(self, card_type: str, evidence_span: str, card_id: str = None) -> dict:
        current_time = time.time()
        
        handled_key = f"{card_type}:{evidence_span}"
        if handled_key in self.handled_cards:
            time_since_handled = current_time - self.handled_cards[handled_key]
            if time_since_handled < self.SUPPRESSION_WINDOW:
                return {
                    "show": False,
                    "reason": "recently_handled",
                    "suppressed_for": self.SUPPRESSION_WINDOW - time_since_handled,
                    "message": f"Card for '{card_type}' already shown {time_since_handled:.0f}s ago"
                }
        
        if card_type in self.cooldowns:
            time_since_last = current_time - self.cooldowns[card_type]
            cooldown_period = self.COOLDOWN_WINDOWS.get(card_type, self.COOLDOWN_WINDOWS["default"])
            
            if time_since_last < cooldown_period:
                return {
                    "show": False,
                    "reason": "cooldown_active",
                    "cooldown_remaining": cooldown_period - time_since_last,
                    "message": f"Cooldown active for '{card_type}' ({cooldown_period - time_since_last:.0f}s remaining)"
                }
        
        if self._is_duplicate_evidence(evidence_span):
            return {
                "show": False,
                "reason": "duplicate_evidence",
                "message": "Same evidence span triggered multiple cards"
            }
        
        self.evidence_history.append({
            "span": evidence_span,
            "timestamp": current_time,
            "card_type": card_type
        })
        
        return {
            "show": True,
            "reason": "allowed",
            "message": "Card passes all suppression checks"
        }
    
    def mark_handled(self, card_type: str, evidence_span: str):
        current_time = time.time()
        handled_key = f"{card_type}:{evidence_span}"
        
        self.handled_cards[handled_key] = current_time
        self.cooldowns[card_type] = current_time
        
        self._cleanup_old_entries()
    
    def _is_duplicate_evidence(self, evidence_span: str) -> bool:
        current_time = time.time()
        recent_window = 30
        
        for entry in self.evidence_history:
            if entry["span"] == evidence_span:
                if current_time - entry["timestamp"] < recent_window:
                    return True
        
        return False
    
    def _cleanup_old_entries(self):
        current_time = time.time()
        max_age = 600
        
        self.handled_cards = {
            k: v for k, v in self.handled_cards.items()
            if current_time - v < max_age
        }
        
        self.cooldowns = {
            k: v for k, v in self.cooldowns.items()
            if current_time - v < self.COOLDOWN_WINDOWS.get(k, self.COOLDOWN_WINDOWS["default"])
        }
    
    def get_suppression_status(self) -> dict:
        current_time = time.time()
        
        active_suppressions = []
        for key, timestamp in self.handled_cards.items():
            remaining = self.SUPPRESSION_WINDOW - (current_time - timestamp)
            if remaining > 0:
                active_suppressions.append({
                    "key": key,
                    "remaining_seconds": remaining
                })
        
        active_cooldowns = []
        for card_type, timestamp in self.cooldowns.items():
            cooldown_period = self.COOLDOWN_WINDOWS.get(card_type, self.COOLDOWN_WINDOWS["default"])
            remaining = cooldown_period - (current_time - timestamp)
            if remaining > 0:
                active_cooldowns.append({
                    "type": card_type,
                    "remaining_seconds": remaining
                })
        
        return {
            "active_suppressions": active_suppressions,
            "active_cooldowns": active_cooldowns,
            "evidence_history_size": len(self.evidence_history)
        }
    
    def reset(self):
        self.handled_cards.clear()
        self.cooldowns.clear()
        self.evidence_history.clear()
