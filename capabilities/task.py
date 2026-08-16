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


def verify_goal(status, evidence=""):
    """Validate the agent's explicit goal verification decision.

    The capability itself does not inspect the world. Brain owns the task
    state and only accepts a verified state when fresh evidence exists.
    """

    normalized = str(status or "").strip().lower()

    if normalized not in {"verified", "failed", "uncertain"}:
        return {
            "success": False,
            "error": "invalid_verification_status",
            "output": (
                "status должен быть verified, failed или uncertain."
            ),
        }

    evidence = str(evidence or "").strip()

    if not evidence:
        return {
            "success": False,
            "error": "verification_evidence_required",
            "output": "Для проверки цели необходимо указать evidence.",
        }

    return {
        "success": True,
        "data": {
            "status": normalized,
            "evidence": evidence[:2000],
        },
        "output": (
            "Цель отмечена как "
            + normalized
            + "."
        ),
    }


def finish_task():
    """Validate the terminal task action.

    Brain performs the actual semantic verification and owns task state.
    This capability only provides the terminal execution primitive.
    """
    return {
        "success": True,
        "data": {
            "operation": "finish",
        },
        "output": "Задача завершена.",
    }
