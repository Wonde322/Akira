import threading
import time

from agent_runtime import AgentRuntime
from akira_gateway import AkiraGateway
from request_context import create_request_context


def test_runtime_cancellation_is_cooperative_and_structured():
    started = threading.Event()
    cancelled = threading.Event()

    def executor(goal, session_id=None):
        started.set()
        while not cancelled.is_set():
            from execution_context import execution_cancelled
            if execution_cancelled():
                cancelled.set()
                break
            time.sleep(0.001)
        return "late result"

    runtime = AgentRuntime(executor=executor)
    result_holder = []

    def run():
        result_holder.append(runtime.run("долгая задача", task_id="request-1"))

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(1.0)
    assert runtime.is_active("request-1")
    assert runtime.cancel("request-1") is True
    thread.join(1.0)

    assert not thread.is_alive()
    assert result_holder == [{
        "success": False,
        "error": "cancelled",
        "output": "Выполнение отменено.",
    }]
    assert not runtime.is_active("request-1")


def test_gateway_preserves_request_identity_for_cancellation():
    class FakeRuntime:
        def __init__(self):
            self.calls = []
            self.cancelled = []

        def run(self, request, **kwargs):
            self.calls.append((request.request_id, kwargs))
            return {"success": True, "output": "ok"}

        def cancel(self, request_id):
            self.cancelled.append(request_id)
            return True

    runtime = FakeRuntime()
    gateway = AkiraGateway(runtime=runtime)
    result = gateway.submit_text("привет", request_id="request-2")

    assert result["success"] is True
    assert runtime.calls == [("request-2", {"task_id": "request-2"})]
    assert gateway.cancel("request-2") is True
    assert runtime.cancelled == ["request-2"]


def test_runtime_rejects_duplicate_active_task_ids():
    entered = threading.Event()
    release = threading.Event()

    def executor(goal, session_id=None):
        entered.set()
        release.wait(1.0)
        return "done"

    runtime = AgentRuntime(executor=executor)
    thread = threading.Thread(target=lambda: runtime.run("задача", task_id="same"))
    thread.start()
    assert entered.wait(1.0)

    try:
        runtime.run("вторая задача", task_id="same")
    except RuntimeError as exc:
        assert "already active" in str(exc)
    else:
        raise AssertionError("duplicate task id was accepted")
    finally:
        release.set()
        thread.join(1.0)
