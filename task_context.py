"""Link observed desktop patterns to currently active Akira tasks."""
from __future__ import annotations

import re

_STOP_WORDS = {
    "и", "в", "во", "на", "с", "со", "для", "по", "к", "из", "что", "как",
    "the", "a", "an", "to", "of", "for", "and", "with", "in", "on",
}


def _tokens(value):
    return {
        token.lower()
        for token in re.findall(r"[\w-]+", str(value or ""), flags=re.UNICODE)
        if len(token) >= 3 and token.lower() not in _STOP_WORDS
    }


class TaskContextLinker:
    """Find the active task most plausibly related to a desktop context."""

    def __init__(self, runtime=None):
        self._runtime = runtime

    def _tasks(self):
        runtime = self._runtime
        if runtime is None:
            from task_runtime import get_runtime
            runtime = get_runtime()
        try:
            result = runtime.list_tasks(limit=50)
            return result.get("tasks", []) if result.get("success") else []
        except Exception:
            return []

    @staticmethod
    def _score(task, context):
        goal = str(task.get("goal") or "")
        app = str((context or {}).get("app") or "")
        title = str((context or {}).get("title") or "")
        goal_tokens = _tokens(goal)
        context_tokens = _tokens(app + " " + title)
        if not goal_tokens or not context_tokens:
            return 0.0
        overlap = goal_tokens & context_tokens
        if not overlap:
            return 0.0
        return round(len(overlap) / max(1, min(len(goal_tokens), len(context_tokens))), 3)

    def match(self, context):
        candidates = []
        for task in self._tasks():
            if task.get("status") not in {"queued", "running"}:
                continue
            score = self._score(task, context)
            if score <= 0:
                continue
            candidates.append((score, task))
        if not candidates:
            return None
        score, task = max(candidates, key=lambda item: item[0])
        return {
            "task_id": task.get("id"),
            "goal": task.get("goal"),
            "status": task.get("status"),
            "confidence": score,
        }


def link_context_to_active_task(context, runtime=None):
    return TaskContextLinker(runtime=runtime).match(context)
