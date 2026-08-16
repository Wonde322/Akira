
"""Internal task planning capability for Akira."""

def plan_task(steps):
    if not isinstance(steps, list):
        return {
            "success": False,
            "error": "invalid_plan",
            "output": "steps должен быть массивом строк.",
        }

    steps = [str(step).strip() for step in steps if str(step).strip()]

    if not steps:
        return {
            "success": False,
            "error": "empty_plan",
            "output": "План пуст.",
        }

    return {
        "success": True,
        "data": {
            "steps": steps[:20],
            "count": min(len(steps), 20),
        },
        "output": "План создан.",
    }


def update_task_plan(steps):
    return plan_task(steps)
