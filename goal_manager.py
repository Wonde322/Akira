from datetime import datetime, timezone


class GoalInitiative:
    """
    Связывает существующие goals и tasks.
    Сам ничего не исполняет: возвращает предложения для
    существующего ProactiveRuntime.
    """

    def __init__(self, goal_source=None, task_runtime=None):
        self.goal_source = goal_source
        self.task_runtime = task_runtime

    def get_goals(self):
        source = self.goal_source

        if source is None:
            return []

        for name in ("get_goals", "list_goals", "analyze_goals"):
            method = getattr(source, name, None)

            if callable(method):
                try:
                    result = method()
                except TypeError:
                    continue

                if isinstance(result, dict):
                    return result.get("goals", [])

                if isinstance(result, (list, tuple)):
                    return list(result)

        return []

    def get_tasks(self):
        runtime = self.task_runtime

        if runtime is None:
            return []

        tasks = getattr(runtime, "tasks", {})

        if isinstance(tasks, dict):
            return [
                {"task_id": task_id, **task}
                for task_id, task in tasks.items()
                if isinstance(task, dict)
            ]

        return list(tasks) if isinstance(tasks, (list, tuple)) else []

    def analyze(self):
        goals = self.get_goals()
        tasks = self.get_tasks()
        suggestions = []

        active_tasks = [
            task for task in tasks
            if task.get("status") in {"running", "paused"}
        ]

        for goal in goals:
            if isinstance(goal, dict):
                goal_id = goal.get("id") or goal.get("goal_id")
                goal_text = (
                    goal.get("goal")
                    or goal.get("text")
                    or goal.get("description")
                    or ""
                )
            else:
                goal_id = None
                goal_text = str(goal)

            related = [
                task for task in active_tasks
                if goal_id and (
                    task.get("goal_id") == goal_id
                    or task.get("parent_goal_id") == goal_id
                )
            ]

            if not related and goal_text:
                suggestions.append({
                    "type": "goal.unattended",
                    "goal_id": goal_id,
                    "goal": goal_text,
                    "action": "suggest",
                    "message": (
                        f"Есть цель без активной задачи: {goal_text}"
                    ),
                })

        return suggestions

    def run_once(self):
        return {
            "success": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "suggestions": self.analyze(),
        }
