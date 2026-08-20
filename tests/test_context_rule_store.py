from context_rule_store import ContextRuleStore
from proactive_runtime import ProactiveAction, ProactiveRuntime


def test_rule_store_persists_rules(tmp_path):
    path = tmp_path / "rules.json"
    store = ContextRuleStore(path)
    rule = store.add({"app": "Figma", "message": "Проверь сетку"})
    restored = ContextRuleStore(path)
    assert restored.list()[0]["id"] == rule["id"]
    assert restored.list()[0]["app"] == "Figma"


def test_disabled_rule_is_not_active(tmp_path):
    store = ContextRuleStore(tmp_path / "rules.json")
    rule = store.add({"app": "Figma", "message": "Проверь"})
    store.set_enabled(rule["id"], False)
    assert store.active() == []


def test_runtime_rule_survives_recreation(tmp_path):
    store = ContextRuleStore(tmp_path / "rules.json")
    runtime = ProactiveRuntime(context_rule_store=store, desktop_cooldown_seconds=0)
    rule = runtime.add_context_rule(app="Figma", message="Проверь сетку")
    recreated = ProactiveRuntime(context_rule_store=ContextRuleStore(store.path), desktop_cooldown_seconds=0)
    event = {"type": "desktop.changed", "payload": {"previous_ui": {"app": "Finder"}, "ui": {"app": "Figma"}}}
    decision = recreated.decide(event)
    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason == "context_rule:" + rule["id"]


def test_runtime_can_disable_and_remove_rule(tmp_path):
    store = ContextRuleStore(tmp_path / "rules.json")
    runtime = ProactiveRuntime(context_rule_store=store)
    rule = runtime.add_context_rule(app="Figma", message="Проверь")
    assert runtime.set_context_rule_enabled(rule["id"], False)["enabled"] is False
    assert runtime.remove_context_rule(rule["id"]) is True
    assert runtime.context_rules() == []
