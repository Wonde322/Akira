import pytest

from proactive_interruption_control import ProactiveInterruptionControl


def make(tmp_path, now=1000.0):
    clock = [now]
    control = ProactiveInterruptionControl(
        path=str(tmp_path / "interruption.json"), clock=lambda: clock[0]
    )
    return control, clock


def test_defaults_to_normal(tmp_path):
    control, _ = make(tmp_path)
    assert control.snapshot() == {"mode": "normal", "quiet_until": None}


def test_normal_allows_regular_question(tmp_path):
    control, _ = make(tmp_path)
    assert control.allow("ask_user", "normal") is True


def test_focus_blocks_regular_question(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("focus")
    assert control.allow("ask_user", "normal") is False


def test_focus_allows_low_priority_notification(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("focus")
    assert control.allow("notify", "low") is True


def test_focus_blocks_normal_notification(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("focus")
    assert control.allow("notify", "normal") is False


def test_quiet_blocks_low_priority_notification(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("quiet")
    assert control.allow("notify", "low") is False


def test_high_priority_bypasses_focus(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("focus")
    assert control.allow("ask_user", "high") is True


def test_high_priority_bypasses_quiet(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("quiet")
    assert control.allow("notify", "high") is True


def test_timed_quiet_expires(tmp_path):
    control, clock = make(tmp_path)
    control.set_mode("quiet", duration_seconds=30)
    assert control.snapshot()["mode"] == "quiet"
    clock[0] += 31
    assert control.snapshot() == {"mode": "normal", "quiet_until": None}


def test_mode_persists_across_restart(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("focus")
    restarted = ProactiveInterruptionControl(path=str(tmp_path / "interruption.json"))
    assert restarted.snapshot()["mode"] == "focus"


def test_invalid_mode_is_rejected(tmp_path):
    control, _ = make(tmp_path)
    with pytest.raises(ValueError):
        control.set_mode("party")


def test_nonpositive_quiet_duration_is_rejected(tmp_path):
    control, _ = make(tmp_path)
    with pytest.raises(ValueError):
        control.set_mode("quiet", duration_seconds=0)


def test_reset_returns_to_normal(tmp_path):
    control, _ = make(tmp_path)
    control.set_mode("quiet")
    assert control.reset() == {"mode": "normal", "quiet_until": None}
