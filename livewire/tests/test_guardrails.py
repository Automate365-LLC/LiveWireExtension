import pytest
from services.guardrails import GuardrailEngine
import time

def test_debounce():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 1
    
    assert guardrails.should_show_card("price") == True
    assert guardrails.should_show_card("timing") == False
    time.sleep(1.1)
    assert guardrails.should_show_card("timing") == True

def test_dedupe():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    
    assert guardrails.should_show_card("price") == True
    assert guardrails.should_show_card("price") == False
    assert guardrails.should_show_card("timing") == True

def test_rate_limit():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    guardrails.MAX_CARDS_PER_5MIN = 3
    
    assert guardrails.should_show_card("price") == True
    assert guardrails.should_show_card("timing") == True
    assert guardrails.should_show_card("authority") == True
    assert guardrails.should_show_card("need") == False

def test_reset():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    
    guardrails.should_show_card("price")
    guardrails.should_show_card("timing")
    guardrails.reset()
    
    assert guardrails.last_card_time is None
    assert len(guardrails.recent_objections) == 0

def test_different_objection_types():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    
    assert guardrails.should_show_card("price") == True
    assert guardrails.should_show_card("timing") == True
    assert guardrails.should_show_card("authority") == True

def test_get_stats():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    
    guardrails.should_show_card("price")
    stats = guardrails.get_stats()
    
    assert "cards_shown_last_5min" in stats
    assert stats["cards_shown_last_5min"] == 1

def test_alternating_objections():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    
    assert guardrails.should_show_card("price") == True
    assert guardrails.should_show_card("timing") == True
    assert guardrails.should_show_card("price") == True

def test_max_tracking():
    guardrails = GuardrailEngine()
    guardrails.DEBOUNCE_SECONDS = 0
    guardrails.MAX_CARDS_PER_5MIN = 15
    
    for i in range(15):
        guardrails.should_show_card(f"objection_{i}")
    
    assert len(guardrails.recent_objections) == 10
    assert len(guardrails.objection_timestamps) == 10