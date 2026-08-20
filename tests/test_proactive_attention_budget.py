from proactive_attention_budget import ProactiveAttentionBudget
from proactive_inbox import ProactiveInbox
from proactive_runtime import ProactiveRuntime


class Clock:
    def __init__(self, value=0.0): self.value = value
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class Budget:
    def __init__(self, allowed=True): self.allowed = allowed; self.calls = []
    def allow(self, action, priority="normal"):
        self.calls.append((getattr(action, "value", action), priority))
        return self.allowed


def event(number):
    return {"id": f"attention-{number}", "type": "proactive.question",
            "payload": {"question": f"Question {number}"}}


def test_budget_starts_full(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=3, clock=Clock())
    assert budget.snapshot()["points"] == 3.0


def test_normal_notification_consumes_one_point(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=3, clock=Clock())
    assert budget.allow("notify", "normal")
    assert budget.snapshot()["points"] == 2.0


def test_question_costs_more_than_notification(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=3, clock=Clock())
    assert budget.allow("ask_user", "normal")
    assert budget.snapshot()["points"] == 1.0


def test_low_priority_notification_has_smaller_cost(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=1, clock=Clock())
    assert budget.allow("notify", "low")
    assert budget.allow("notify", "low")
    assert not budget.allow("notify", "low")


def test_budget_blocks_when_exhausted(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=1, clock=Clock())
    assert budget.allow("notify", "normal")
    assert not budget.allow("notify", "normal")


def test_budget_refills_with_time(tmp_path):
    clock = Clock()
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=2, refill_seconds=10, clock=clock)
    assert budget.allow("ask_user", "normal")
    assert budget.snapshot()["points"] == 0.0
    clock.advance(10)
    assert budget.allow("notify", "normal")


def test_high_priority_bypasses_budget(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=1, clock=Clock())
    assert budget.allow("notify", "normal")
    assert budget.allow("ask_user", "high")
    assert budget.snapshot()["points"] == 0.0


def test_budget_survives_restart(tmp_path):
    path = str(tmp_path / "budget.json")
    clock = Clock()
    first = ProactiveAttentionBudget(path, max_points=2, clock=clock)
    first.allow("notify", "normal")
    second = ProactiveAttentionBudget(path, max_points=2, clock=clock)
    assert second.snapshot()["points"] == 1.0


def test_reset_restores_full_budget(tmp_path):
    budget = ProactiveAttentionBudget(str(tmp_path / "budget.json"), max_points=2, clock=Clock())
    budget.allow("ask_user", "normal")
    assert budget.reset()["points"] == 2.0


def test_runtime_delivers_when_budget_allows(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    budget = Budget(True)
    runtime = ProactiveRuntime(dedupe_seconds=0, inbox=inbox, attention_budget=budget)
    result = runtime.handle(event(1))
    assert result["attention"]["action"] == "ask_user"
    assert budget.calls == [("ask_user", "high")]


def test_runtime_suppresses_when_budget_is_exhausted(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    budget = Budget(False)
    runtime = ProactiveRuntime(dedupe_seconds=0, inbox=inbox, attention_budget=budget)
    result = runtime.handle(event(2))
    assert result["attention"] == {"suppressed": True, "reason": "attention_budget"}
    assert inbox.list() == []


def test_runtime_never_calls_budget_for_record_only_decision(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    budget = Budget(True)
    runtime = ProactiveRuntime(dedupe_seconds=0, inbox=inbox, attention_budget=budget)
    result = runtime.handle({"id": "record", "type": "unknown", "payload": {}})
    assert result["attention"] is None
    assert budget.calls == []
