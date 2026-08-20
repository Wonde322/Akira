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


def test_proactive_text_prefers_message():
    window = object.__new__(ProactiveMainWindow)
    assert window._proactive_text({"message": "hello", "title": "ignored"}) == "hello"


def test_submit_proactive_answer_does_not_use_brain_worker():
    window = object.__new__(ProactiveMainWindow)
    window.proactive_surface = FakeSurface()
    window.voice = FakeVoice(dialogue=False)
    messages = []
    states = []
    cleared = []
    window._append_message = lambda text, role: messages.append((text, role))
    window._clear_status = lambda: cleared.append(True)
    window._set_state = lambda state: states.append(state)

    handled = window._submit_proactive_answer("yes")

    assert handled is True
    assert messages == [("yes", "user")]
    assert window.proactive_surface.answers == ["yes"]
    assert cleared == [True]
    assert states == [window.IDLE]


def test_submit_returns_false_without_active_question():
    window = object.__new__(ProactiveMainWindow)
    window.proactive_surface = FakeSurface(active=None)
    assert window._submit_proactive_answer("normal message") is False
