
"""Persistent in-process background task runtime for Akira.

A background task gets its own Session and executes independently
from the foreground conversation.

Architecture:

    foreground ask()
          |
          +---- background_task_start()
                       |
                       v
                 TaskRuntime
                       |
                 ThreadPoolExecutor
                       |
                       v
                    brain.ask()
                       |
                       v
                 persistent result

The runtime deliberately does not expose arbitrary Python execution.
The background task receives a natural-language goal and goes through
the same Akira brain/tool/permission architecture as a foreground task.
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

TASK_DIR = (
    ROOT
    / "runtime"
    / "tasks"
)

TASK_FILE = (
    ROOT
    / "runtime"
    / "background_tasks.json"
)

MAX_CONCURRENT_TASKS = 3
MAX_STORED_TASKS = 100


class TaskRuntime:
    """Threaded autonomous task manager."""

    def __init__(
        self,
        max_workers=MAX_CONCURRENT_TASKS,
    ):
        self.max_workers = max_workers

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="akira-bg",
        )

        self._lock = threading.RLock()

        self._tasks = {}
        self._futures = {}

        self._load()

    # ========================================================
    # Persistence
    # ========================================================

    def _load(self):
        TASK_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not TASK_FILE.exists():
            return

        try:
            payload = json.loads(
                TASK_FILE.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return

        if not isinstance(payload, list):
            return

        for task in payload[-MAX_STORED_TASKS:]:
            if not isinstance(task, dict):
                continue

            task_id = task.get("id")

            if not task_id:
                continue

            # A process restart means an old worker no longer exists.
            if task.get("status") == "running":
                task["status"] = "interrupted"
                task["error"] = (
                    "Akira process was restarted "
                    "before this background task completed."
                )
                task["finished_at"] = (
                    datetime.now().isoformat(
                        timespec="seconds",
                    )
                )

            self._tasks[task_id] = task

    def _save(self):
        TASK_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = list(
            self._tasks.values()
        )[-MAX_STORED_TASKS:]

        temporary = TASK_FILE.with_suffix(
            ".json.tmp"
        )

        temporary.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            TASK_FILE
        )

    # ========================================================
    # Task helpers
    # ========================================================

    def _active_count(self):
        return sum(
            1
            for task in self._tasks.values()
            if task.get("status") == "running"
        )

    def _make_task(
        self,
        goal,
        session_id=None,
    ):
        task_id = uuid.uuid4().hex[:12]

        now = datetime.now().isoformat(
            timespec="seconds"
        )

        return {
            "id": task_id,
            "goal": str(goal).strip(),
            "session_id": (
                session_id
                or f"background:{task_id}"
            ),
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }

    # ========================================================
    # Spawn
    # ========================================================

    def spawn(
        self,
        goal,
        session_id=None,
    ):
        goal = str(goal or "").strip()

        if not goal:
            return {
                "success": False,
                "error": "empty_goal",
                "output": (
                    "Нельзя создать background task "
                    "с пустой целью."
                ),
            }

        with self._lock:

            if self._active_count() >= self.max_workers:
                return {
                    "success": False,
                    "error": "background_capacity",
                    "output": (
                        "Достигнут лимит одновременно "
                        f"работающих background tasks: "
                        f"{self.max_workers}."
                    ),
                }

            task = self._make_task(
                goal,
                session_id,
            )

            task_id = task["id"]

            self._tasks[task_id] = task
            self._save()

            future = self._executor.submit(
                self._run,
                task_id,
            )

            self._futures[task_id] = future

            task["status"] = "running"
            task["started_at"] = (
                datetime.now().isoformat(
                    timespec="seconds",
                )
            )

            self._save()

        return {
            "success": True,
            "task_id": task_id,
            "status": "running",
            "goal": goal,
            "output": (
                f"Background task {task_id} "
                "запущен."
            ),
        }

    # ========================================================
    # Worker
    # ========================================================

    def _run(self, task_id):
        try:

            with self._lock:
                task = self._tasks.get(
                    task_id
                )

                if task is None:
                    return

                goal = task["goal"]
                session_id = task[
                    "session_id"
                ]

            # Import lazily.
            # Это важно: task_runtime должен импортироваться
            # без немедленного создания LLM client.
            from brain import ask

            result = ask(
                goal,
                session_id=session_id,
            )

            with self._lock:

                task = self._tasks.get(
                    task_id
                )

                if task is None:
                    return

                task["status"] = "completed"
                task["result"] = str(
                    result
                )
                task["finished_at"] = (
                    datetime.now().isoformat(
                        timespec="seconds",
                    )
                )

                task["error"] = None

                self._save()

        except Exception as error:

            with self._lock:

                task = self._tasks.get(
                    task_id
                )

                if task is None:
                    return

                task["status"] = "failed"
                task["error"] = str(
                    error
                )
                task["result"] = None
                task["finished_at"] = (
                    datetime.now().isoformat(
                        timespec="seconds",
                    )
                )

                task["traceback"] = (
                    traceback.format_exc()
                )[-4000:]

                self._save()

        finally:

            with self._lock:
                self._futures.pop(
                    task_id,
                    None,
                )

                self._save()

    # ========================================================
    # Status
    # ========================================================

    def status(self, task_id):
        with self._lock:

            task = self._tasks.get(
                str(task_id)
            )

            if task is None:
                return {
                    "success": False,
                    "error": "task_not_found",
                    "output": (
                        f"Task {task_id} не найден."
                    ),
                }

            return {
                "success": True,
                "task": dict(task),
                "output": json.dumps(
                    task,
                    ensure_ascii=False,
                    indent=2,
                ),
            }

    # ========================================================
    # List
    # ========================================================

    def list_tasks(
        self,
        limit=20,
    ):
        try:
            limit = int(limit)
        except Exception:
            limit = 20

        limit = max(
            1,
            min(limit, 50),
        )

        with self._lock:

            tasks = list(
                self._tasks.values()
            )[-limit:]

            tasks.reverse()

            return {
                "success": True,
                "tasks": tasks,
                "output": json.dumps(
                    tasks,
                    ensure_ascii=False,
                    indent=2,
                ),
            }

    # ========================================================
    # Result
    # ========================================================

    def result(
        self,
        task_id,
    ):
        response = self.status(
            task_id
        )

        if not response.get("success"):
            return response

        task = response["task"]

        status = task.get(
            "status"
        )

        if status == "completed":
            return {
                "success": True,
                "ready": True,
                "task_id": task_id,
                "result": task.get(
                    "result"
                ),
                "output": str(
                    task.get("result")
                    or ""
                ),
            }

        if status == "failed":
            return {
                "success": False,
                "ready": True,
                "task_id": task_id,
                "error": task.get(
                    "error"
                ),
                "output": (
                    "Background task failed: "
                    + str(
                        task.get("error")
                        or ""
                    )
                ),
            }

        return {
            "success": True,
            "ready": False,
            "task_id": task_id,
            "status": status,
            "output": (
                f"Task {task_id} ещё выполняется."
            ),
        }


_runtime = None
_runtime_lock = threading.Lock()


def get_runtime():
    global _runtime

    if _runtime is None:
        with _runtime_lock:

            if _runtime is None:
                _runtime = TaskRuntime()

    return _runtime


def background_task_start(
    goal,
):
    return get_runtime().spawn(
        goal
    )


def background_task_status(
    task_id,
):
    return get_runtime().status(
        task_id
    )


def background_tasks(
    limit=20,
):
    return get_runtime().list_tasks(
        limit
    )


def background_task_result(
    task_id,
):
    return get_runtime().result(
        task_id
    )
