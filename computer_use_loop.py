from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComputerUseStep:
    iteration: int
    action: str | None = None
    arguments: dict = field(default_factory=dict)
    before: Any = None
    result: Any = None
    after: Any = None
    changed: bool | None = None


class ComputerUseLoop:
    """Stateful computer-use controller.

    Visual observation is evidence for visual state only. It is not a universal
    postcondition check: applications, files, processes and commands must use
    their authoritative result/state instead of inferring facts from pixels.
    """

    SYSTEM_VERIFIED_ACTIONS = {
        "open", "close", "read", "write", "create", "move", "copy",
        "rename", "delete", "shell", "find",
    }

    def __init__(self, observer, executor, decider=None, verifier=None, max_iterations=20):
        if not callable(observer):
            raise TypeError("observer must be callable")
        if not callable(executor):
            raise TypeError("executor must be callable")
        self.observer = observer
        self.executor = executor
        self.decider = decider
        self.verifier = verifier
        self.max_iterations = max_iterations

    def _observe(self):
        return self.observer()

    def _execute(self, action, arguments):
        arguments = arguments or {}
        try:
            return self.executor(action, arguments)
        except TypeError:
            return self.executor(action=action, arguments=arguments)

    @staticmethod
    def _normalize_decision(decision):
        if decision is None:
            return {"type": "finish"}
        if isinstance(decision, str):
            return {"type": "finish", "answer": decision}
        if not isinstance(decision, dict):
            return {"type": "finish", "answer": decision}
        decision = dict(decision)
        action = decision.get("action") or decision.get("tool") or decision.get("tool_name")
        if action:
            decision["type"] = "action"
            decision["action"] = action
            decision["arguments"] = decision.get("arguments") or decision.get("args") or {}
            return decision
        if str(decision.get("type") or decision.get("status") or "").lower() in {"finish", "done", "completed", "complete", "final"}:
            decision["type"] = "finish"
            return decision
        decision["type"] = "finish"
        return decision

    @staticmethod
    def _did_change(before, after):
        if before is None or after is None:
            return None
        return before != after

    def _decide(self, goal, observation, history):
        if not callable(self.decider):
            return {"type": "finish", "status": "failed", "error": "No computer-use decider configured"}
        context = {"goal": goal, "observation": observation, "history": history}
        try:
            decision = self.decider(goal, context)
        except TypeError:
            try:
                decision = self.decider(context)
            except TypeError:
                decision = self.decider(goal)
        return self._normalize_decision(decision)

    def _needs_visual_observation(self, action, result):
        if str(action).lower() not in self.SYSTEM_VERIFIED_ACTIONS:
            return True
        if not isinstance(result, dict):
            return False
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        return data.get("verification") not in {"process_state", "filesystem_state", "command_result"}

    def _verify(self, goal, action, arguments, result, before, after, changed):
        if not callable(self.verifier):
            if isinstance(result, dict) and result.get("success") is True:
                return {"verified": True, "changed": changed, "source": result.get("data", result).get("verification", "tool_result") if isinstance(result.get("data", result), dict) else "tool_result"}
            return {"verified": False, "changed": changed}
        payload = {"goal": goal, "action": action, "arguments": arguments, "result": result, "before": before, "after": after, "changed": changed}
        try:
            value = self.verifier(**payload)
        except TypeError:
            value = self.verifier(payload)
        if isinstance(value, bool):
            return {"verified": value, "changed": changed}
        return value

    def run(self, goal):
        history = []
        observation = self._observe()
        for iteration in range(1, self.max_iterations + 1):
            decision = self._decide(goal, observation, history)
            if decision.get("type") == "finish":
                status = decision.get("status", "completed")
                return {"success": status == "completed", "status": status, "answer": decision.get("answer"), "iterations": iteration, "history": history, "final_observation": observation}
            action = decision["action"]
            arguments = decision["arguments"]
            step = ComputerUseStep(iteration=iteration, action=action, arguments=arguments, before=observation)
            result = self._execute(action, arguments)
            step.result = result

            # Only actions whose outcome is visual receive a post-action screenshot.
            if self._needs_visual_observation(action, result):
                after = self._observe()
                observation = after
            else:
                after = None
            step.after = after
            step.changed = self._did_change(step.before, after)
            verification = self._verify(goal, action, arguments, result, step.before, after, step.changed)
            history.append({"iteration": step.iteration, "action": step.action, "arguments": step.arguments, "before": step.before, "result": step.result, "after": step.after, "changed": step.changed, "verification": verification})
            if isinstance(verification, dict) and verification.get("terminal"):
                status = verification.get("status", "completed")
                return {"success": status == "completed", "status": status, "iterations": iteration, "history": history, "final_observation": observation}
        return {"success": False, "status": "budget_exhausted", "iterations": self.max_iterations, "history": history, "final_observation": observation}
