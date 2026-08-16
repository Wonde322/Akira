from types import SimpleNamespace


class FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = SimpleNamespace(name=name, arguments=arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message):
        self.choices = [FakeChoice(message)]


class FakeCompletions:
    """Имитирует client.chat.completions с заранее заданной последовательностью ответов."""

    def __init__(self, responses):
        self.iterator = iter(responses)
        self.seen = []

    def create(self, **kwargs):
        self.seen.append(kwargs["messages"])
        return next(self.iterator)


class FakeClient:
    def __init__(self, responses):
        self._completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self._completions)

    @property
    def completions(self):
        return self._completions


def _stub_tool_loop(brain, responses, monkeypatch):
    """Подменяет клиент Groq и возвращает перехватчик сообщений."""
    fake = FakeClient(responses)
    monkeypatch.setattr(brain, "client", fake)
    return fake.completions.seen


def test_ask_stops_after_tool_iteration_limit(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: lambda **kw: "ок")

    count = {"n": 0}

    def endless_tool_calls(**kwargs):
        count["n"] += 1
        tool_call = FakeToolCall(f"call-{count['n']}", "some_tool", "{}")
        return FakeResponse(FakeMessage(tool_calls=[tool_call]))

    fake = FakeClient([])
    fake.chat.completions.create = endless_tool_calls
    monkeypatch.setattr(brain, "client", fake)

    result = brain.ask("запрос")

    assert result == "Достигнут лимит шагов обработки запроса."
    assert count["n"] == brain.MAX_TOOL_ITERATIONS


def test_ask_handles_invalid_json_arguments(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")

    executed = []
    monkeypatch.setattr(
        brain,
        "get_tool_implementation",
        lambda _: lambda **kw: executed.append(kw) or "ок",
    )

    responses = [
        FakeResponse(FakeMessage(
            tool_calls=[FakeToolCall("call-1", "some_tool", "{invalid json")]
        )),
        FakeResponse(FakeMessage(content="обработано")),
    ]

    seen = _stub_tool_loop(brain, responses, monkeypatch)

    result = brain.ask("запрос")

    assert result == "обработано"
    assert executed == []

    tool_messages = [m for m in seen[0] if m["role"] == "tool"]
    assert tool_messages[0]["tool_call_id"] == "call-1"
    assert "ОШИБКА (invalid_arguments)" in tool_messages[0]["content"]


def test_ask_passes_tool_error_back_to_model(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")

    def failing_tool(**kw):
        raise RuntimeError("взрыв")

    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: failing_tool)

    responses = [
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall("call-1", "some_tool", "{}")])),
        FakeResponse(FakeMessage(content="ответ после ошибки")),
    ]

    seen = _stub_tool_loop(brain, responses, monkeypatch)

    result = brain.ask("запрос")

    assert result == "ответ после ошибки"

    tool_messages = [m for m in seen[0] if m["role"] == "tool"]
    assert "ОШИБКА (error)" in tool_messages[0]["content"]
    assert "взрыв" in tool_messages[0]["content"]


def test_ask_persists_tool_calls_and_results_in_history(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: lambda **kw: "результат")

    responses = [
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall("call-1", "some_tool", "{}")])),
        FakeResponse(FakeMessage(content="сделано")),
    ]

    _stub_tool_loop(brain, responses, monkeypatch)

    brain.ask("запрос")

    roles = [message["role"] for message in brain.conversation]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert brain.conversation[2]["tool_call_id"] == "call-1"
    assert brain.conversation[2]["content"] == "результат"
    assert brain.conversation[3]["content"] == "сделано"


def test_execute_tool_returns_structured_failure_without_raising(
    isolated_project, monkeypatch
):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: None)

    result = brain.execute_tool_result("missing", {})

    assert result["success"] is False
    assert result["error"] == "unknown"


def test_tool_result_text_handles_none_output(isolated_project):
    brain = isolated_project("brain")

    assert brain._tool_result_text({
        "success": True,
        "error": None,
        "output": None,
    }) == ""

    assert brain._tool_result_text({
        "success": False,
        "error": "boom",
        "output": None,
    }) == "ОШИБКА (boom): "


def test_long_tool_loop_keeps_user_message(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: lambda **kw: "результат")

    count = {"n": 0}

    def endless_tool_calls(**kwargs):
        count["n"] += 1
        tool_call = FakeToolCall(f"call-{count['n']}", "some_tool", "{}")
        return FakeResponse(FakeMessage(tool_calls=[tool_call]))

    fake = FakeClient([])
    fake.chat.completions.create = endless_tool_calls
    monkeypatch.setattr(brain, "client", fake)

    brain.ask("исходный вопрос")

    roles = [message["role"] for message in brain.conversation]

    assert roles[0] == "user"
    assert brain.conversation[0]["content"] == "исходный вопрос"
    assert brain.conversation[-1]["role"] == "assistant"