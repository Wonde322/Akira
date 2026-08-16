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