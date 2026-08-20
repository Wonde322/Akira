from proactive_runtime import ProactiveRuntime


def test_interrupted_task_finishes_proactive_lifecycle_and_releases_source():
    class Lifecycle:
        def __init__(self): self.calls = []
        def interrupted(self, task_id, reason):
            self.calls.append((task_id, reason))
            return {"task_id": task_id, "status": "interrupted"}

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

    result = runtime._update_lifecycle("task.interrupted", {
        "task_id": "task-1",
        "session_id": "proactive:root-1",
        "error": "process restarted",
    })

    assert result == {"task_id": "task-1", "status": "interrupted"}
    assert lifecycle.calls == [("task-1", "process restarted")]
    assert orchestrator.released == ["source-1"]


def test_interrupted_non_proactive_task_releases_autonomous_source_without_lifecycle():
    class Lifecycle:
        def interrupted(self, *args):
            raise AssertionError("non-proactive task must not touch lifecycle")

    class Orchestrator:
        def __init__(self): self.released = []
        def release(self, source): self.released.append(source)

    orchestrator = Orchestrator()
    runtime = object.__new__(ProactiveRuntime)
    runtime._lifecycle = Lifecycle()
    runtime._orchestrator = orchestrator
    runtime._lock = __import__("threading").RLock()
    runtime._autonomous_sources = {"task-2": "source-2"}

    assert runtime._update_lifecycle("task.interrupted", {"task_id": "task-2"}) is None
    assert orchestrator.released == ["source-2"]
