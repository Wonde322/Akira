from types import SimpleNamespace

from desktop_app.proactive_window import ProactiveMainWindow


class FakeSurface:
    def __init__(self, active="q1", result=None):
        self.active_question_id = active
        self.result = result or {"success": True}
        self.answers = []

    def answer(self, text):
        self.answers.append(text)
        self.active_question_id = None
        return self.result


class FakeVoice:
    def __init__(self, dialogue=False):
        self._dialogue = dialogue
        self.resumed = False

    def is_dialogue(self):
        return self._dialogue

    def resume(self):
        self.resumed = True


def _window(active="q1", dialogue=False):
    """Small duck-typed receiver for testing logic without constructing QWidget."""
    window = SimpleNamespace()
    window.proactive_surface = FakeSurface(active=active)
    window.voice = FakeVoice(dialogue=dialogue)
    window.IDLE = "idle"
    window.LISTENING = "listening"
    window._append_message = lambda text, role: None
    window._clear_status = lambda: None
    window._set_state = lambda state: None
    window._show_error = lambda text: None
    return window


def test_proactive_text_prefers_message():
    window = _window()
    assert ProactiveMainWindow._proactive_text(
        window, {"message": "hello", "title": "ignored"}
    ) == "hello"


def test_submit_proactive_answer_does_not_use_brain_worker():
    window = _window()
    messages = []
    states = []
    cleared = []
    window._append_message = lambda text, role: messages.append((text, role))
    window._clear_status = lambda: cleared.append(True)
    window._set_state = lambda state: states.append(state)

    handled = ProactiveMainWindow._submit_proactive_answer(window, "yes")

    assert handled is True
    assert messages == [("yes", "user")]
    assert window.proactive_surface.answers == ["yes"]
    assert cleared == [True]
    assert states == [window.IDLE]


def test_submit_returns_false_without_active_question():
    window = _window(active=None)
    assert ProactiveMainWindow._submit_proactive_answer(window, "normal message") is False
