import task_runtime
from proactive_runtime import ProactiveRuntime


def test_cancelled_task_emits_terminal_event(monkeypatch):
    emitted = []

    class Future:
        def cancel(self):
            return True

    runtime = object.__new__(task_runtime.TaskRuntime)
    runtime._lock = __import__("threading").RLock()
    runtime._tasks = {
        "task-1": {
            "id": "task-1", "goal": "check context", "session_id": "proactive:root-1",
            "status": "queued", "error": None, "finished_at": None,
            "parent_event_id": "event-1", "correlation_id": "root-1", "causation_depth": 1,
        }
    }
    runtime._futures = {"task-1": Future()}
    runtime._save = lambda: None
    monkeypatch.setattr(runtime, "_emit", lambda event_type, payload, task=None: emitted.append((event_type, payload, task)))

    result = runtime.cancel("task-1", "user cancelled")

    assert result == {"success": True, "task_id": "task-1", "status": "cancelled"}
    assert emitted[0][0] == "task.cancelled"
    assert emitted[0][1]["task_id"] == "task-1"
    assert emitted[0][1]["session_id"] == "proactive:root-1"
    assert emitted[0][1]["error"] == "user cancelled"


def test_proactive_runtime_marks_cancelled_lifecycle_immediately():
    class Lifecycle:
        def __init__(self): self.calls = []
        def cancelled(self, task_id, reason):
            self.calls.append((task_id, reason))
            return {"task_id": task_id, "status": "cancelled"}

    class Orchestrator:
        def __init__(self): self.released = []
        def release(self, source): self.released.append(source)

    lifecycle = Lifecycle()
    orchestrator = Orchestrator()
    runtime = object.__new__(ProactiveRuntime)
    runtime._lifecycle = lifecycle
    runtime._orchestrator = orchestrator
    runtime._lock = __import__("threading").RLock()
    runtime._autonomous_sources = {"task-1": "source-1"}

    result = runtime._update_lifecycle("task.cancelled", {
        "task_id": "task-1", "session_id": "proactive:root-1", "error": "user cancelled",
    })

    assert result == {"task_id": "task-1", "status": "cancelled"}
    assert lifecycle.calls == [("task-1", "user cancelled")]
    assert orchestrator.released == ["source-1"]
