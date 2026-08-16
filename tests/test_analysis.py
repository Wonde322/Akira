from types import SimpleNamespace


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(FakeMessage(content))]


def _stub_client(analysis, monkeypatch, responses):
    """Подменяет клиент Groq и возвращает перехватчик промптов."""
    prompts = []
    iterator = iter(responses)

    def create(**kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        return next(iterator)

    monkeypatch.setattr(
        analysis,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        ),
    )

    return prompts


def test_focuses_are_validated_without_network(isolated_project):
    analysis = isolated_project("analysis")

    assert analysis.FOCUSES == {"period", "goals", "proactive"}
    assert analysis.analyze("unknown", 7) == "Неизвестный фокус анализа: unknown"


def test_unknown_focus_returns_message_before_calling_llm(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")
    called = []
    monkeypatch.setattr(
        analysis,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: called.append(True))
            )
        ),
    )

    result = analysis.analyze("whatever", 3)

    assert result == "Неизвестный фокус анализа: whatever"
    assert called == []


def test_period_focus_returns_early_without_events(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")
    called = []

    monkeypatch.setattr(analysis, "get_events_for_period", lambda days: [])
    monkeypatch.setattr(
        analysis,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: called.append(True))
            )
        ),
    )

    result = analysis.analyze_period()

    assert "нет событий" in result.lower()
    assert called == []


def test_period_focus_does_not_load_full_memory_snapshot(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")
    called = []

    def boom():
        called.append(True)
        raise AssertionError("period не должен грузить полную snapshot")

    monkeypatch.setattr(analysis, "get_memory_snapshot", boom)
    monkeypatch.setattr(analysis, "get_events_for_period", lambda days: [])

    result = analysis.analyze_period()

    assert "нет событий" in result.lower()
    assert called == []


def test_goals_focus_does_load_memory_snapshot(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")

    monkeypatch.setattr(
        analysis,
        "get_memory_snapshot",
        lambda: {"goals": [], "tasks": []},
    )
    monkeypatch.setattr(analysis, "get_activity_totals", lambda days: {})

    prompts = _stub_client(analysis, monkeypatch, [FakeResponse("итог")])

    analysis.analyze_goals()

    assert prompts


def test_goals_focus_builds_context_and_calls_llm(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")

    monkeypatch.setattr(
        analysis,
        "get_memory_snapshot",
        lambda: {"goals": [{"text": "Цель"}], "tasks": []},
    )
    monkeypatch.setattr(analysis, "get_activity_totals", lambda days: {"Editor": 3600})

    prompts = _stub_client(analysis, monkeypatch, [FakeResponse("итог")])

    result = analysis.analyze_goals()

    assert result == "итог"
    assert "ЦЕЛИ" in prompts[0]
    assert "АКТИВНОСТЬ" in prompts[0]
    assert "1 ч" in prompts[0]


def test_wrappers_delegate_to_analyze_with_the_right_focus(
    isolated_project, monkeypatch
):
    analysis = isolated_project("analysis")

    calls = []
    monkeypatch.setattr(
        analysis,
        "analyze",
        lambda focus, days: calls.append((focus, days)) or "ok",
    )

    analysis.analyze_period(14)
    analysis.analyze_goals(30)
    analysis.check_proactive(2)

    assert calls == [("period", 14), ("goals", 30), ("proactive", 2)]


def test_proactive_prompt_mentions_action_levels(isolated_project, monkeypatch):
    analysis = isolated_project("analysis")

    monkeypatch.setattr(
        analysis,
        "get_memory_snapshot",
        lambda: {"goals": [], "tasks": []},
    )
    monkeypatch.setattr(analysis, "get_activity_totals", lambda days: {})

    prompts = _stub_client(analysis, monkeypatch, [FakeResponse("NO_ACTION")])

    result = analysis.check_proactive()

    assert result == "NO_ACTION"
    assert "INFO" in prompts[0]
    assert "ATTENTION" in prompts[0]
    assert "URGENT" in prompts[0]