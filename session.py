"""Минимальная абстракция сессии для изоляции историй разговора."""

from datetime import datetime
from uuid import uuid4


class Session:
    """Изолированная история разговора одного источника запросов.

    Помимо истории хранит лёгкое состояние текущей computer-use задачи
    (без байтов изображений и без дублирования сообщений).
    """

    def __init__(self, session_id=None, max_history=12):
        self.session_id = session_id or uuid4().hex
        self.max_history = max_history
        self.history = []
        self.task = None

    def add(self, message):
        self.history.append(message)

    def begin_task(self, goal):
        """Начинает computer-use задачу. Никаких байтов изображений."""
        self.task = {
            "goal": goal,
            "step": 0,
            "last_observation": None,
            "last_action": None,
            "last_action_arguments": None,
            "last_result": None,
            "no_progress_count": 0,
            "actions_without_observe": 0,
            "recovery_count": 0,
            "failed_actions": [],
            "successful_actions": [],

            "action_history": [],
            "recovery_context": None,
            "recovery_tools": [],

            # План выполнения. Это состояние агента, а не история чата.
            "plan": [],
            "plan_index": 0,
            "plan_completed": [],
            "plan_failed": [],
            "plan_revision": 0,

            # Последняя оценка состояния цели.
            "goal_status": "in_progress",
            "goal_evidence": None,
            "goal_verification": {
                "status": "unverified",
                "evidence": None,
                "observation_step": None,
                "verified_at": None,
            },

            # Tool router state.
            "selected_tools": [],
            "tool_router_history": [],

            # Capabilities, найденные через полный registry.
            # Они остаются доступными следующим reasoning-итерациям.
            "discovered_tools": [],
            "discovery_history": [],

            "started_at": datetime.now().isoformat(timespec="seconds"),
        }

        return self.task

    def end_task(self):
        """Завершает текущую задачу и очищает состояние."""
        self.task = None

    def register_action(self, action, arguments=None):
        """Фиксирует state-changing действие."""
        if self.task is None:
            return

        self.task["last_action"] = action
        self.task["last_action_arguments"] = arguments
        self.task["actions_without_observe"] += 1

    def register_result(self, action, result):
        """Запоминает результат действия для следующего шага reasoning."""
        if self.task is None:
            return

        task = self.task
        task["last_result"] = {
            "action": action,
            "success": bool(result.get("success")),
            "error": result.get("error"),
            "output": str(result.get("output") or "")[:2000],
        }

        if result.get("success"):
            task["successful_actions"].append(action)
            task["successful_actions"] = task["successful_actions"][-20:]
        else:
            task["failed_actions"].append({
                "action": action,
                "error": result.get("error"),
                "output": str(result.get("output") or "")[:1000],
            })
            task["failed_actions"] = task["failed_actions"][-20:]

    def register_recovery(self):
        """Фиксирует попытку восстановления после неудачи."""
        if self.task is not None:
            self.task["recovery_count"] += 1

    def register_action_history(
        self,
        action,
        arguments=None,
        result=None,
        recovery=None,
    ):
        """Stores execution evidence for adaptive recovery."""
        if self.task is None:
            return

        result = result if isinstance(result, dict) else {}

        entry = {
            "action": str(action or ""),
            "arguments": arguments or {},
            "success": bool(result.get("success")),
            "error": result.get("error"),
            "output": str(result.get("output") or "")[:1000],
        }

        self.task["action_history"].append(entry)
        self.task["action_history"] = (
            self.task["action_history"][-30:]
        )

        if recovery and recovery.get("failed"):
            self.task["recovery_context"] = recovery
            self.task["recovery_tools"] = list(
                recovery.get("fallback_tools") or []
            )[:12]
        else:
            self.clear_recovery()

    def clear_recovery(self):
        """Clears the current recovery recommendation."""
        if self.task is None:
            return

        self.task["recovery_context"] = None
        self.task["recovery_tools"] = []

    def set_plan(self, steps):
        """Устанавливает/заменяет план текущей задачи."""
        if self.task is None:
            return

        normalized = []

        for step in steps or []:
            if isinstance(step, str):
                text = step.strip()
            elif isinstance(step, dict):
                text = str(step.get("description") or step.get("step") or "").strip()
            else:
                text = ""

            if text:
                normalized.append(text)

        self.task["plan"] = normalized[:20]
        self.task["plan_index"] = 0
        self.task["plan_completed"] = []
        self.task["plan_failed"] = []
        self.task["plan_revision"] += 1

    def current_plan_step(self):
        if self.task is None:
            return None

        plan = self.task["plan"]
        index = self.task["plan_index"]

        if not plan or index >= len(plan):
            return None

        return plan[index]

    def complete_plan_step(self, evidence=None):
        if self.task is None:
            return

        task = self.task
        index = task["plan_index"]

        if index < len(task["plan"]):
            task["plan_completed"].append({
                "step": task["plan"][index],
                "evidence": str(evidence or "")[:1000],
            })
            task["plan_index"] += 1

    def fail_plan_step(self, reason=None):
        if self.task is None:
            return

        task = self.task
        index = task["plan_index"]

        if index < len(task["plan"]):
            task["plan_failed"].append({
                "step": task["plan"][index],
                "reason": str(reason or "")[:1000],
            })

    def set_goal_status(self, status, evidence=None):
        if self.task is None:
            return

        self.task["goal_status"] = status
        self.task["goal_evidence"] = str(evidence or "")[:2000]

    def set_goal_verification(self, status, evidence=None):
        """Stores terminal verification state for the current task."""
        if self.task is None:
            return

        task = self.task
        normalized = str(status or "unverified").strip().lower()

        task["goal_verification"] = {
            "status": normalized,
            "evidence": str(evidence or "")[:2000],
            "observation_step": task.get("step"),
            "verified_at": (
                datetime.now().isoformat(timespec="seconds")
                if normalized == "verified"
                else None
            ),
        }

        if normalized == "verified":
            task["goal_status"] = "verified"
            task["goal_evidence"] = str(evidence or "")[:2000]
        elif normalized == "failed":
            task["goal_status"] = "failed"
            task["goal_evidence"] = str(evidence or "")[:2000]
        else:
            task["goal_status"] = "in_progress"
            task["goal_evidence"] = str(evidence or "")[:2000]

    def goal_is_verified(self):
        if self.task is None:
            return False

        verification = self.task.get(
            "goal_verification",
            {},
        )

        return (
            verification.get("status") == "verified"
            and verification.get("observation_step") == self.task.get("step")
        )


    def register_observation(self, observation):
        """Фиксирует новое наблюдение: счётчик шагов и no-progress."""
        if self.task is None:
            return

        task = self.task
        task["step"] += 1
        task["actions_without_observe"] = 0

        previous = task["last_observation"]
        previous_hash = previous.get("hash") if previous else None

        if observation.hash and observation.hash == previous_hash:
            task["no_progress_count"] += 1
        elif observation.hash:
            task["no_progress_count"] = 1
        else:
            task["no_progress_count"] = 0

        task["last_observation"] = observation.to_dict()

    def trim(self):
        """Обрезает историю, не разрывая пары assistant→tool.

        Гарантирует, что история (если непуста) начинается с сообщения
        role="user", а сообщения assistant с tool_calls всегда сопровождаются
        своими tool-ответами. Это защищает следующий ход модели от контекста
        без user-запроса или с оборванной парой tool_calls→tool.
        """
        if len(self.history) <= self.max_history:
            return

        messages = self.history[-self.max_history:]

        while messages and messages[0]["role"] == "tool":
            messages.pop(0)

        # Двигаемся вперёд до границы turn (user), отбрасывая осиротевшие
        # assistant-сообщения вместе с их tool-ответами.
        while messages and messages[0]["role"] != "user":
            message = messages.pop(0)

            if message["role"] == "assistant" and message.get("tool_calls"):
                while messages and messages[0]["role"] == "tool":
                    messages.pop(0)

        self.history[:] = messages
