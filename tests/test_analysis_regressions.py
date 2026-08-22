import analysis


def test_analyze_rejects_invalid_days():
    assert "days должен" in analysis.analyze_period(0)
    assert "days должен" in analysis.analyze_period(True)


def test_analyze_clamps_large_day_range(monkeypatch):
    monkeypatch.setattr(analysis, "get_activity_totals", lambda days: {})
    monkeypatch.setattr(analysis, "get_memory_snapshot", lambda: {"goals": [], "tasks": []})

    class Response:
        class choices:
            class message:
                content = "ok"
            choices = [type("Choice", (), {"message": message})()]

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert "3650 дней" in kwargs["messages"][0]["content"]
                    return Response()

    monkeypatch.setattr(analysis, "client", Client())
    assert analysis.analyze_goals(999999) == "ok"


def test_analyze_handles_empty_model_response(monkeypatch):
    monkeypatch.setattr(analysis, "get_events_for_period", lambda days: [{"time": "t", "text": "x"}])

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    choice = type("Choice", (), {"message": type("Message", (), {"content": "  "})()})()
                    return type("Response", (), {"choices": [choice]})()

    monkeypatch.setattr(analysis, "client", Client())
    assert "не вернул" in analysis.analyze_period(1)
