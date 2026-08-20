"""Control and recovery helpers for user-approved proactive actions."""
from __future__ import annotations


class ProactiveActionController:
    """Coordinates lifecycle state with the background task runtime."""

    def __init__(self, runtime, lifecycle):
        self._runtime = runtime
        self._lifecycle = lifecycle

    def recover(self):
        """Reconcile persisted lifecycle entries after process startup."""
        try:
            result = self._runtime.list_tasks(limit=100)
        except Exception:
            return []
        if not isinstance(result, dict): return []
        tasks = result.get("tasks")
        if not isinstance(tasks, list): return []
        return self._lifecycle.reconcile(tasks)

    def cancel(self, task_id):
        item = self._lifecycle.get(task_id)
        if item is None:
            return {"success": False, "error": "proactive_action_not_found", "task_id": str(task_id)}
        try:
            result = self._runtime.cancel(task_id)
        except Exception as exc:
            return {"success": False, "error": str(exc), "task_id": str(task_id)}
        if not isinstance(result, dict):
            return {"success": False, "error": "invalid_runtime_response", "task_id": str(task_id)}
        if result.get("success"):
            result = dict(result)
            result["lifecycle"] = self._lifecycle.cancelled(task_id)
        return result

    def status(self, task_id):
        lifecycle = self._lifecycle.get(task_id)
        try:
            runtime = self._runtime.status(task_id)
        except Exception as exc:
            runtime = {"success": False, "error": str(exc), "task_id": str(task_id)}
        if not isinstance(runtime, dict): runtime = {"success": False, "error": "invalid_runtime_response", "task_id": str(task_id)}
        return {"success": bool(runtime.get("success")), "task_id": str(task_id), "lifecycle": lifecycle, "runtime": runtime}


def get_proactive_action_controller(runtime=None, lifecycle=None):
    if runtime is None:
        from task_runtime import get_runtime
        runtime = get_runtime()
    if lifecycle is None:
        from proactive_action_lifecycle import get_proactive_action_lifecycle
        lifecycle = get_proactive_action_lifecycle()
    return ProactiveActionController(runtime, lifecycle)
