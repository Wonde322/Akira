from awareness import AwarenessRuntime


class Patterns:
    def observe(self, ui):
        return [{"type": "desktop.context.dwell", "context": {"app": "Figma"}, "message": "dwell"}]


class Linker:
    def match(self, context):
        assert context["app"] == "Figma"
        return {"task_id": "task-1", "goal": "Проверить Figma макет", "status": "running", "confidence": 0.8}


def test_pattern_is_enriched_with_related_active_task():
    runtime = AwarenessRuntime(pattern_engine=Patterns(), task_context_linker=Linker())
    insight = runtime._enrich_pattern({"type": "desktop.context.dwell", "context": {"app": "Figma"}})
    assert insight["active_task"]["task_id"] == "task-1"


def test_pattern_without_match_stays_valid():
    class NoMatch:
        def match(self, context): return None
    runtime = AwarenessRuntime(pattern_engine=Patterns(), task_context_linker=NoMatch())
    insight = runtime._enrich_pattern({"type": "desktop.context.dwell", "context": {"app": "Figma"}})
    assert "active_task" not in insight
