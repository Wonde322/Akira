from context_patterns import ContextPatternEngine
from proactive_runtime import ProactiveAction, ProactiveRuntime


def test_context_pattern_engine_emits_dwell_once_per_visit():
    engine = ContextPatternEngine(dwell_seconds=60, cooldown_seconds=0, clock=lambda: 0)
    assert engine.observe({"app": "Figma", "title": "Poster"}, now=0) == []
    insights = engine.observe({"app": "Figma", "title": "Poster"}, now=61)
    assert len(insights) == 1
    assert insights[0]["type"] == "desktop.context.dwell"
    assert engine.observe({"app": "Figma", "title": "Poster"}, now=120) == []


def test_context_pattern_engine_detects_repeated_returns():
    engine = ContextPatternEngine(revisit_count=3, revisit_window_seconds=600, cooldown_seconds=0)
    engine.observe({"app": "Figma"}, now=0)
    engine.observe({"app": "Chrome"}, now=10)
    engine.observe({"app": "Figma"}, now=20)
    engine.observe({"app": "Chrome"}, now=30)
    insights = engine.observe({"app": "Figma"}, now=40)
    assert len(insights) == 1
    assert insights[0]["type"] == "desktop.context.repeated"
    assert insights[0]["count"] == 3


def test_old_visits_do_not_trigger_repeated_pattern():
    engine = ContextPatternEngine(revisit_count=3, revisit_window_seconds=30, cooldown_seconds=0)
    engine.observe({"app": "Figma"}, now=0)
    engine.observe({"app": "Chrome"}, now=10)
    engine.observe({"app": "Figma"}, now=20)
    engine.observe({"app": "Chrome"}, now=100)
    assert engine.observe({"app": "Figma"}, now=110) == []


def test_runtime_notifies_for_dwell_pattern():
    runtime = ProactiveRuntime()
    decision = runtime.decide({
        "id": "dwell-1",
        "type": "desktop.context.dwell",
        "payload": {"message": "Ты уже около 15 мин находишься в Figma."},
    })
    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason == "context_dwell"
    assert decision.priority == "low"


def test_runtime_notifies_for_repeated_context_pattern():
    runtime = ProactiveRuntime()
    decision = runtime.decide({
        "id": "repeat-1",
        "type": "desktop.context.repeated",
        "payload": {"message": "Ты уже 3 раз возвращался к Figma."},
    })
    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason == "context_repeated"
    assert decision.priority == "normal"
