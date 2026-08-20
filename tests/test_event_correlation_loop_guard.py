import event_bus


def test_trigger_remembers_root_correlation_once():
    trigger = {"recent_correlations": []}
    bus = object.__new__(event_bus.EventBus)

    bus._remember_correlation(trigger, "root-1")
    bus._remember_correlation(trigger, "root-1")

    assert trigger["recent_correlations"] == ["root-1"]


def test_trigger_recognizes_same_causal_chain():
    bus = object.__new__(event_bus.EventBus)
    trigger = {"recent_correlations": ["root-1"]}

    assert bus._correlation_seen(trigger, "root-1") is True
    assert bus._correlation_seen(trigger, "root-2") is False


def test_trigger_correlation_history_is_bounded(monkeypatch):
    monkeypatch.setattr(event_bus, "MAX_TRIGGER_CORRELATIONS", 3)
    bus = object.__new__(event_bus.EventBus)
    trigger = {"recent_correlations": []}

    for index in range(5):
        bus._remember_correlation(trigger, f"root-{index}")

    assert trigger["recent_correlations"] == ["root-2", "root-3", "root-4"]


def test_trigger_state_without_history_is_backward_compatible():
    bus = object.__new__(event_bus.EventBus)
    trigger = {"id": "legacy"}

    assert bus._correlation_seen(trigger, "root-1") is False
    bus._remember_correlation(trigger, "root-1")
    assert trigger["recent_correlations"] == ["root-1"]
