from context_triggers import ContextTriggerEngine, changed_context, ui_context
from proactive_runtime import ProactiveAction, ProactiveRuntime


def event(payload):
    return {"id": "evt-1", "type": "desktop.changed", "payload": payload}


def test_ui_context_accepts_backend_key_variants():
    assert ui_context({"application": "Figma", "window_title": "Poster"}) == {
        "app": "Figma", "title": "Poster"
    }
    assert ui_context(None) == {"app": "", "title": ""}


def test_changed_context_distinguishes_app_and_title_changes():
    delta = changed_context(
        {"app": "Figma", "title": "A"},
        {"app": "Chrome", "title": "B"},
    )
    assert delta["app_changed"] is True
    assert delta["title_changed"] is True


def test_context_rule_matches_only_target_context():
    engine = ContextTriggerEngine([{
        "id": "figma-review",
        "app": "Figma",
        "title": "Review",
        "message": "Пора посмотреть макет",
    }])
    matches = engine.match({
        "previous_ui": {"app": "Chrome", "title": "Mail"},
        "ui": {"application": "Figma", "window_title": "Client Review"},
    })
    assert len(matches) == 1
    assert matches[0]["rule"]["id"] == "figma-review"
    assert matches[0]["message"] == "Пора посмотреть макет"


def test_runtime_notifies_when_context_rule_matches():
    runtime = ProactiveRuntime(
        desktop_cooldown_seconds=0,
        context_rules=[{
            "id": "figma",
            "app": "Figma",
            "message": "Ты открыл Figma.",
            "priority": "high",
        }],
    )
    decision = runtime.decide(event({
        "changed_fields": ["ui"],
        "previous_ui": {"app": "Chrome", "title": "Mail"},
        "ui": {"app": "Figma", "title": "Poster"},
    }))
    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason == "context_rule:figma"
    assert decision.notification == "Ты открыл Figma."
    assert decision.priority == "high"


def test_runtime_asks_when_context_rule_requests_answer():
    runtime = ProactiveRuntime(
        desktop_cooldown_seconds=0,
        context_rules=[{
            "id": "terminal-check",
            "app": "Terminal",
            "action": "ask_user",
            "message": "Продолжить работу с задачей?",
        }],
    )
    decision = runtime.decide(event({
        "previous_ui": {"app": "Figma"},
        "ui": {"app": "Terminal"},
    }))
    assert decision.action == ProactiveAction.ASK_USER
    assert decision.reason == "context_rule:terminal-check"


def test_unmatched_context_stays_quiet():
    runtime = ProactiveRuntime(
        desktop_cooldown_seconds=0,
        context_rules=[{"id": "figma", "app": "Figma"}],
    )
    decision = runtime.decide(event({
        "previous_ui": {"app": "Chrome"},
        "ui": {"app": "Terminal"},
    }))
    assert decision.action == ProactiveAction.RECORD
    assert decision.reason.startswith("desktop_changed:")
