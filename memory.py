import copy
import json
import os
import tempfile
from datetime import datetime, timedelta


MEMORY_FILE = "memory.json"
COLLECTION_FIELDS = ("goals", "tasks", "events", "activity")


class MemoryCorruptionError(RuntimeError):
    """Raised when an existing memory file cannot be safely read."""


def _empty_memory():
    return {
        "goals": [],
        "tasks": [],
        "events": [],
        "activity": [],
    }


def _normalize_memory(data):
    """Keep existing data while making required collections safe to consume."""
    memory = data.copy() if isinstance(data, dict) else {}

    for field in COLLECTION_FIELDS:
        if not isinstance(memory.get(field), list):
            memory[field] = []

    memory["goals"] = [
        {
            "text": "",
            "created": "",
            **goal,
        }
        for goal in memory["goals"]
        if isinstance(goal, dict)
    ]
    memory["tasks"] = [
        {
            "text": "",
            "goal": None,
            "completed": False,
            "created": "",
            **task,
        }
        for task in memory["tasks"]
        if isinstance(task, dict)
    ]
    memory["events"] = [
        {
            "text": "",
            "time": "",
            **event,
        }
        for event in memory["events"]
        if isinstance(event, dict)
    ]
    memory["activity"] = [
        {
            "app": "Неизвестно",
            "started": "",
            "ended": "",
            "duration_seconds": 0,
            **session,
        }
        for session in memory["activity"]
        if isinstance(session, dict)
    ]

    return memory


def load_memory():
    """Load the current memory state. This module owns all file access."""
    if not os.path.exists(MEMORY_FILE):
        return _empty_memory()

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MemoryCorruptionError(
            "Файл памяти повреждён и не может быть безопасно прочитан."
        ) from error

    if not isinstance(data, dict):
        raise MemoryCorruptionError(
            "Файл памяти имеет недопустимую структуру."
        )

    return _normalize_memory(data)


def save_memory(memory):
    """Atomically replace memory.json after a complete JSON write succeeds."""
    directory = os.path.dirname(os.path.abspath(MEMORY_FILE))
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".memory-",
        suffix=".tmp",
        dir=directory,
    )

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(_normalize_memory(memory), file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, MEMORY_FILE)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def get_memory_snapshot():
    """Return a copy of the current memory for read-only consumers."""
    return copy.deepcopy(load_memory())


def _update_memory(update):
    memory = load_memory()
    update(memory)
    save_memory(memory)


def add_goal(goal: str) -> str:
    def update(memory):
        memory["goals"].append({
            "text": goal,
            "created": datetime.now().isoformat(timespec="seconds"),
        })

    _update_memory(update)
    return "Цель сохранена: " + goal


def get_goals(limit: int = 20) -> str:
    goals = load_memory()["goals"]

    if not goals:
        return "Сохранённых целей пока нет."

    result = "Текущие цели:\n"

    for number, goal in enumerate(goals[-limit:], 1):
        result += str(number) + ". " + goal["text"] + "\n"

    return result.strip()


def add_task(task: str, goal: str = None) -> str:
    def update(memory):
        memory["tasks"].append({
            "text": task,
            "goal": goal,
            "completed": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        })

    _update_memory(update)

    if goal:
        return "Задача добавлена: " + task + " → цель: " + goal

    return "Задача добавлена: " + task


def get_tasks() -> str:
    active_tasks = [
        task for task in load_memory()["tasks"]
        if not task["completed"]
    ]

    if not active_tasks:
        return "Активных задач нет."

    result = "Текущие задачи:\n"

    for number, task in enumerate(active_tasks, 1):
        result += str(number) + ". " + task["text"] + "\n"

    return result.strip()


def complete_task(task_text: str) -> str:
    completed_task = None

    def update(memory):
        nonlocal completed_task

        for task in memory["tasks"]:
            if not task["completed"] and task_text.lower() in task["text"].lower():
                task["completed"] = True
                task["completed_at"] = datetime.now().isoformat(timespec="seconds")
                completed_task = task["text"]
                return

    _update_memory(update)

    if completed_task is not None:
        return "Задача выполнена: " + completed_task

    return "Я не нашёл такую активную задачу."


def add_event(event: str) -> str:
    def update(memory):
        memory["events"].append({
            "text": event,
            "time": datetime.now().isoformat(timespec="seconds"),
        })

    _update_memory(update)
    return "Событие записано."


def get_recent_events(limit: int = 20) -> str:
    events = load_memory()["events"][-limit:]

    if not events:
        return "История событий пока пуста."

    result = "Последние события:\n"

    for event in events:
        result += event["time"] + " — " + event["text"] + "\n"

    return result.strip()


def get_events_for_period(days: int = 7):
    cutoff = datetime.now() - timedelta(days=days)
    events = []

    for event in load_memory()["events"]:
        try:
            event_time = datetime.fromisoformat(event["time"])
        except (KeyError, TypeError, ValueError):
            continue

        if event_time >= cutoff:
            events.append(event)

    return events


def add_activity_session(
    app_name: str,
    started_at: str,
    ended_at: str,
    duration_seconds: int,
):
    def update(memory):
        memory["activity"].append({
            "app": app_name,
            "started": started_at,
            "ended": ended_at,
            "duration_seconds": duration_seconds,
        })

    _update_memory(update)


def get_activity():
    return copy.deepcopy(load_memory()["activity"])


def get_activity_for_period(days: int = 1):
    cutoff = datetime.now() - timedelta(days=days)
    activity = []

    for session in load_memory()["activity"]:
        try:
            started = datetime.fromisoformat(session["started"])
        except (KeyError, TypeError, ValueError):
            continue

        if started >= cutoff:
            activity.append(session)

    return activity


def get_activity_totals(days: int = 1):
    totals = {}

    for session in get_activity_for_period(days):
        try:
            app = session["app"]
            duration = session["duration_seconds"]
        except KeyError:
            continue

        if not isinstance(duration, (int, float)):
            continue

        totals[app] = totals.get(app, 0) + duration

    return totals
