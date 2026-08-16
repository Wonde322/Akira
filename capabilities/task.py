"""Internal execution-plan capability for Akira.

The capability validates structured planning operations.
Actual mutable task state belongs to Session.
"""


def _normalize_steps(steps):
    if not isinstance(steps, list):
        return None

    result = []

    for step in steps:
        if isinstance(step, str):
            text = step.strip()
        elif isinstance(step, dict):
            text = str(
                step.get("description")
                or step.get("step")
                or ""
            ).strip()
        else:
            text = ""

        if text:
            result.append(text)

    return result[:20]


def plan_task(steps):
    normalized = _normalize_steps(steps)

    if not normalized:
        return {
            "success": False,
            "error": "empty_plan",
            "output": "Невозможно создать пустой план.",
        }

    return {
        "success": True,
        "data": {
            "operation": "create",
            "steps": normalized,
            "count": len(normalized),
        },
        "output": "План создан.",
    }


def update_task_plan(steps):
    normalized = _normalize_steps(steps)

    if not normalized:
        return {
            "success": False,
            "error": "empty_plan",
            "output": "Невозможно установить пустой план.",
        }

    return {
        "success": True,
        "data": {
            "operation": "update",
            "steps": normalized,
            "count": len(normalized),
        },
        "output": "План обновлён.",
    }


def complete_plan_step(evidence=""):
    return {
        "success": True,
        "data": {
            "operation": "complete",
            "evidence": str(evidence or "")[:2000],
        },
        "output": "Текущий шаг отмечен как выполненный.",
    }


def fail_plan_step(reason=""):
    return {
        "success": True,
        "data": {
            "operation": "fail",
            "reason": str(reason or "")[:2000],
        },
        "output": "Текущий шаг отмечен как не выполненный.",
    }
