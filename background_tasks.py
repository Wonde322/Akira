"""Runtime for isolated long-running Akira tasks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from config import BACKGROUND_TASK_MAX_CONCURRENT, BACKGROUND_TASK_MAX_STORED

_lock = RLock()
_executor = ThreadPoolExecutor(
    max_workers=BACKGROUND_TASK_MAX_CONCURRENT,
    thread_name_prefix="akira-background",
)
_tasks = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _snapshot(task):
    return {
        key: value
        for key, value in task.items()
        if key != "future"
    }


def _trim():
    if len(_tasks) <= BACKGROUND_TASK_MAX_STORED:
        return

    finished = [
        (task_id, task)
        for task_id, task in _tasks.items()
        if task["status"] in {"completed", "failed"}
    ]
    finished.sort(key=lambda item: item[1].get("finished_at") or "")

    for task_id, _ in finished:
        if len(_tasks) <= BACKGROUND_TASK_MAX_STORED:
            break
        _tasks.pop(task_id, None)


def _run(task_id):
    with _lock:
        task = _tasks.get(task_id)
        if task is None:
            return
        task["status"] = "running"
        task["started_at"] = _now()

    try:
        # Lazy import avoids a brain -> registry -> background circular import.
        from brain import ask

        result = ask(
            task["goal"],
            session_id=task["session_id"],
        )

        with _lock:
            task = _tasks.get(task_id)
            if task is not None:
                task["status"] = "completed"
                task["result"] = str(result or "")
                task["finished_at"] = _now()

    except Exception as exc:
        with _lock:
            task = _tasks.get(task_id)
            if task is not None:
                task["status"] = "failed"
                task["error"] = repr(exc)
                task["finished_at"] = _now()


def background_task_start(goal):
    goal = str(goal or "").strip()
    if not goal:
        return {
            "success": False,
            "error": "empty_background_goal",
            "output": "Для фоновой задачи нужна конкретная цель.",
        }

    task_id = "bg-" + uuid4().hex
    session_id = "background:" + task_id
    task = {
        "task_id": task_id,
        "session_id": session_id,
        "goal": goal[:8000],
        "status": "queued",
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }

    with _lock:
        _trim()
        _tasks[task_id] = task
        task["future"] = _executor.submit(_run, task_id)

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "status": "queued",
        },
        "output": "Фоновая задача запущена: " + task_id,
    }


def background_task_status(task_id):
    with _lock:
        task = _tasks.get(str(task_id or ""))
        if task is None:
            return {
                "success": False,
                "error": "background_task_not_found",
                "output": "Фоновая задача не найдена.",
            }
        data = _snapshot(task)
        data.pop("result", None)
        data.pop("error", None)

    return {
        "success": True,
        "data": data,
        "output": "Статус фоновой задачи: " + data["status"],
    }


def background_task_result(task_id):
    with _lock:
        task = _tasks.get(str(task_id or ""))
        if task is None:
            return {
                "success": False,
                "error": "background_task_not_found",
                "output": "Фоновая задача не найдена.",
            }
        data = _snapshot(task)

    if data["status"] in {"queued", "running"}:
        return {
            "success": True,
            "data": data,
            "output": "Фоновая задача ещё выполняется.",
        }

    if data["status"] == "failed":
        return {
            "success": False,
            "error": "background_task_failed",
            "data": data,
            "output": "Фоновая задача завершилась с ошибкой.",
        }

    return {
        "success": True,
        "data": data,
        "output": data.get("result") or "Фоновая задача завершена.",
    }
