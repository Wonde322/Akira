"""Task lifecycle manager for foreground and background agent work."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from config import BACKGROUND_TASK_MAX_CONCURRENT, BACKGROUND_TASK_MAX_STORED
from agent_runtime import get_agent_runtime


TERMINAL = {"completed", "failed", "cancelled"}


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ManagedTask:
    goal: str
    mode: str
    session_id: str
    task_id: str = field(default_factory=lambda: "task-" + uuid4().hex)
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    future: object = field(default=None, repr=False)

    def snapshot(self, include_result=True):
        data = {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if include_result:
            data["result"] = self.result
            data["error"] = self.error
        return data


class TaskManager:
    """Owns task identity, lifecycle and execution mode.

    Agent reasoning itself belongs to AgentRuntime.  This manager deliberately
    does not know about LLMs, sessions internals, tools or UI.
    """

    def __init__(self, max_workers=BACKGROUND_TASK_MAX_CONCURRENT):
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="akira-task",
        )
        self._tasks = {}
        self._max_stored = BACKGROUND_TASK_MAX_STORED

    def _trim_locked(self):
        if len(self._tasks) <= self._max_stored:
            return
        finished = [
            task for task in self._tasks.values()
            if task.status in TERMINAL
        ]
        finished.sort(key=lambda task: task.finished_at or "")
        for task in finished:
            if len(self._tasks) <= self._max_stored:
                break
            self._tasks.pop(task.task_id, None)

    def _new_task(self, goal, mode, session_id=None):
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("Task requires a non-empty goal")
        task = ManagedTask(
            goal=goal[:8000],
            mode=mode,
            session_id=session_id or ("task:" + uuid4().hex),
        )
        self._tasks[task.task_id] = task
        self._trim_locked()
        return task

    def run_foreground(self, goal, session_id=None):
        with self._lock:
            task = self._new_task(goal, "foreground", session_id)
            task.status = "running"
            task.started_at = _now()
        return self._run(task.task_id)

    def start_background(self, goal, session_id=None):
        with self._lock:
            active = sum(
                1 for task in self._tasks.values()
                if task.mode == "background" and task.status in {"queued", "running"}
            )
            if active >= BACKGROUND_TASK_MAX_CONCURRENT:
                return {
                    "success": False,
                    "error": "background_capacity",
                    "output": "Достигнут лимит одновременно работающих фоновых задач.",
                }
            try:
                task = self._new_task(
                    goal,
                    "background",
                    session_id or ("background:" + uuid4().hex),
                )
            except ValueError:
                return {
                    "success": False,
                    "error": "empty_background_goal",
                    "output": "Для фоновой задачи нужна конкретная цель.",
                }
            task.future = self._executor.submit(self._run, task.task_id)
            return {
                "success": True,
                "data": {"task_id": task.task_id, "status": task.status},
                "output": "Фоновая задача запущена: " + task.task_id,
            }

    def _run(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if task.status == "cancelled":
                return None
            task.status = "running"
            task.started_at = task.started_at or _now()
            goal = task.goal
            session_id = task.session_id
            mode = task.mode

        try:
            result = get_agent_runtime().run(
                goal,
                session_id=session_id,
                mode=mode,
                task_id=task_id,
            )
        except Exception as exc:
            with self._lock:
                task = self._tasks.get(task_id)
                if task is not None and task.status != "cancelled":
                    task.status = "failed"
                    task.error = repr(exc)
                    task.finished_at = _now()
            raise

        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and task.status != "cancelled":
                task.status = "completed"
                task.result = str(result or "")
                task.finished_at = _now()
        return result

    def cancel(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id or ""))
            if task is None:
                return {"success": False, "error": "background_task_not_found"}
            if task.status in TERMINAL:
                return {"success": False, "error": "task_not_active", "status": task.status}
            future = task.future
            if future is not None and future.cancel():
                task.status = "cancelled"
                task.finished_at = _now()
                return {"success": True, "data": task.snapshot(False)}
            return {
                "success": False,
                "error": "task_already_running",
                "status": task.status,
                "output": "Уже выполняемая задача будет отменяться на границе agent step.",
            }

    def status(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id or ""))
            if task is None:
                return {
                    "success": False,
                    "error": "background_task_not_found",
                    "output": "Фоновая задача не найдена.",
                }
            data = task.snapshot(False)
        return {
            "success": True,
            "data": data,
            "output": "Статус фоновой задачи: " + data["status"],
        }

    def result(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id or ""))
            if task is None:
                return {
                    "success": False,
                    "error": "background_task_not_found",
                    "output": "Фоновая задача не найдена.",
                }
            data = task.snapshot(True)

        if data["status"] in {"queued", "running"}:
            return {
                "success": True,
                "data": data,
                "output": "Фоновая задача ещё выполняется.",
            }
        if data["status"] in {"failed", "cancelled"}:
            return {
                "success": False,
                "error": "background_task_failed",
                "data": data,
                "output": "Фоновая задача завершилась без результата.",
            }
        return {
            "success": True,
            "data": data,
            "output": data.get("result") or "Фоновая задача завершена.",
        }


_default_manager = TaskManager()


def get_task_manager():
    return _default_manager
