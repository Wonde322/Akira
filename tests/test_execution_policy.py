from execution_context import current_execution
from execution_policy import ExecutionPolicy, choose_execution_policy
from agent_runtime import AgentRuntime


def test_explicit_policy_wins():
    assert choose_execution_policy("сравни варианты", mode="direct") is ExecutionPolicy.DIRECT


def test_background_is_autonomous():
    assert choose_execution_policy("простая задача", mode="background") is ExecutionPolicy.AUTONOMOUS


def test_simple_known_action_is_direct():
    assert choose_execution_policy("открой калькулятор") is ExecutionPolicy.DIRECT


def test_known_single_operation_is_controlled():
    assert choose_execution_policy("создать файл отчёта на рабочем столе") is ExecutionPolicy.CONTROLLED


def test_complex_request_uses_agent():
    assert choose_execution_policy("исследуй рынок и сравни пять вариантов") is ExecutionPolicy.AGENT


def test_runtime_exposes_selected_policy_in_execution_context():
    seen = []

    def executor(goal, session_id=None):
        seen.append(current_execution().mode)
        return "ok"

    runtime = AgentRuntime(executor=executor)
    assert runtime.run("открой калькулятор") == "ok"
    assert seen == ["direct"]
