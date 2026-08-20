from proactive_attention_budget import ProactiveAttentionBudget
from proactive_interruption_control import ProactiveInterruptionControl


def make(tmp_path):
    now = [1000.0]
    control = ProactiveInterruptionControl(path=str(tmp_path / "control.json"), clock=lambda: now[0])
    budget = ProactiveAttentionBudget(
        path=str(tmp_path / "budget.json"), clock=lambda: now[0], interruption_control=control
    )
    return control, budget


def test_quiet_blocks_delivery_before_budget_is_spent(tmp_path):
    control, budget = make(tmp_path)
    control.set_mode("quiet")
    before = budget.snapshot()["points"]
    assert budget.allow("notify", "normal") is False
    assert budget.snapshot()["points"] == before


def test_focus_allows_low_notification_and_charges_budget(tmp_path):
    control, budget = make(tmp_path)
    control.set_mode("focus")
    before = budget.snapshot()["points"]
    assert budget.allow("notify", "low") is True
    assert budget.snapshot()["points"] == before - 0.5


def test_high_priority_bypasses_quiet_and_has_no_budget_cost(tmp_path):
    control, budget = make(tmp_path)
    control.set_mode("quiet")
    before = budget.snapshot()["points"]
    assert budget.allow("ask_user", "high") is True
    assert budget.snapshot()["points"] == before
