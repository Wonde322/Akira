import contextlib
import copy
import fcntl
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta

from config import MEMORY_FILE


COLLECTION_FIELDS = (
    "goals",
    "tasks",
    "events",
    "activity",

    # Memory 2.0
    # semantic: устойчивые факты / предпочтения пользователя
    # episodic: конкретные прошлые события/эпизоды
    # procedural: успешные способы выполнения повторяющихся задач
    "facts",
    "preferences",
    "episodes",
    "procedures",
)

_process_lock = threading.RLock()


@contextlib.contextmanager
def _locked_memory():
    """Serializes read-modify-write across threads and processes.

    fcntl.flock guards concurrent processes; the in-process RLock guards
    threads of the same process (flock is process-scoped on some platforms).
    The lock lives on a separate, never-replaced file so os.replace-based
    atomic writes cannot break mutual exclusion.
    """
    with _process_lock:
        lock_path = MEMORY_FILE + ".lock"

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


class MemoryCorruptionError(RuntimeError):
    """Raised when an existing memory file cannot be safely read."""


def _empty_memory():
    return {
        "goals": [],
        "tasks": [],
        "events": [],
        "activity": [],

        # Semantic memory.
        "facts": [],
        "preferences": [],

        # Episodic memory.
        "episodes": [],

        # Procedural memory.
        "procedures": [],
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

    # --------------------------------------------------------
    # Memory 2.0 collections
    # --------------------------------------------------------

    memory["facts"] = [
        {
            "key": "",
            "value": "",
            "category": "fact",
            "source": "unknown",
            "confidence": 1.0,
            "created": "",
            "updated": "",
            **fact,
        }
        for fact in memory["facts"]
        if isinstance(fact, dict)
    ]

    memory["preferences"] = [
        {
            "key": "",
            "value": "",
            "source": "unknown",
            "confidence": 1.0,
            "created": "",
            "updated": "",
            **preference,
        }
        for preference in memory["preferences"]
        if isinstance(preference, dict)
    ]

    memory["episodes"] = [
        {
            "summary": "",
            "context": "",
            "importance": 0.5,
            "tags": [],
            "created": "",
            **episode,
        }
        for episode in memory["episodes"]
        if isinstance(episode, dict)
    ]

    memory["procedures"] = [
        {
            "name": "",
            "steps": [],
            "success_count": 0,
            "created": "",
            "updated": "",
            **procedure,
        }
        for procedure in memory["procedures"]
        if isinstance(procedure, dict)
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
    with _locked_memory():
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


# ============================================================
# MEMORY 2.0
# ============================================================
#
# Three persistent layers live in the same atomic store:
#
#   semantic    -> facts/preferences
#   episodic    -> concrete events/episodes
#   procedural  -> successful reusable ways of doing things
#
# Working memory remains in Session and is intentionally NOT persisted
# here as a replacement for current execution state.
# ============================================================


def _memory_tokens(text):
    """Small dependency-free tokenizer for local memory retrieval."""

    import re

    stopwords = {
        "и", "или", "а", "но", "что", "это", "как", "мне", "ты", "я",
        "в", "на", "из", "по", "для", "с", "со", "у", "к", "от", "до",
        "the", "a", "an", "and", "or", "to", "of", "for", "in", "on",
        "with", "is", "it", "my", "me",
    }

    tokens = re.findall(
        r"[a-zA-Zа-яА-ЯёЁ0-9_]+",
        str(text or "").lower(),
    )

    return {
        token
        for token in tokens
        if token not in stopwords and len(token) > 1
    }


def _memory_score(query, text, importance=0.0):
    query_tokens = _memory_tokens(query)
    text_tokens = _memory_tokens(text)

    if not query_tokens or not text_tokens:
        return 0.0

    overlap = query_tokens & text_tokens

    if not overlap:
        return 0.0

    score = float(len(overlap))

    # Exact phrase is a strong signal.
    normalized_query = " ".join(str(query or "").lower().split())
    normalized_text = " ".join(str(text or "").lower().split())

    if normalized_query and normalized_query in normalized_text:
        score += 6.0

    score += float(importance or 0.0)

    return score


def remember_memory(
    content: str,
    kind: str = "fact",
    key: str = "",
    source: str = "user",
    importance: float = 0.7,
):
    """Store durable memory in the appropriate persistent layer.

    kind:
        fact       -> semantic fact
        preference -> semantic preference
        episode    -> episodic memory
        procedure  -> procedural memory

    This function deliberately keeps the schema simple and human-readable.
    """

    content = str(content or "").strip()
    kind = str(kind or "fact").strip().lower()
    key = str(key or "").strip()
    source = str(source or "user").strip()

    if not content:
        return {
            "success": False,
            "error": "empty_memory",
            "output": "Нельзя сохранить пустую память.",
        }

    allowed = {
        "fact",
        "preference",
        "episode",
        "procedure",
    }

    if kind not in allowed:
        return {
            "success": False,
            "error": "invalid_memory_kind",
            "output": (
                "kind должен быть fact, preference, episode или procedure."
            ),
        }

    importance = max(
        0.0,
        min(float(importance or 0.0), 1.0),
    )

    now = datetime.now().isoformat(timespec="seconds")

    def update(memory):
        if kind == "fact":
            # Same key = update existing semantic fact rather than
            # accumulating contradictory duplicates.
            target = None

            if key:
                for item in memory["facts"]:
                    if item.get("key", "").lower() == key.lower():
                        target = item
                        break

            if target is None:
                memory["facts"].append({
                    "key": key or content[:80],
                    "value": content,
                    "category": "fact",
                    "source": source,
                    "confidence": importance,
                    "created": now,
                    "updated": now,
                })
            else:
                target.update({
                    "value": content,
                    "source": source,
                    "confidence": importance,
                    "updated": now,
                })

        elif kind == "preference":
            target = None

            if key:
                for item in memory["preferences"]:
                    if item.get("key", "").lower() == key.lower():
                        target = item
                        break

            if target is None:
                memory["preferences"].append({
                    "key": key or content[:80],
                    "value": content,
                    "source": source,
                    "confidence": importance,
                    "created": now,
                    "updated": now,
                })
            else:
                target.update({
                    "value": content,
                    "source": source,
                    "confidence": importance,
                    "updated": now,
                })

        elif kind == "episode":
            memory["episodes"].append({
                "summary": content,
                "context": key,
                "importance": importance,
                "tags": [],
                "created": now,
            })

            memory["episodes"] = memory["episodes"][-500:]

        elif kind == "procedure":
            target = None

            if key:
                for item in memory["procedures"]:
                    if item.get("name", "").lower() == key.lower():
                        target = item
                        break

            if target is None:
                memory["procedures"].append({
                    "name": key or content[:80],
                    "steps": [content],
                    "success_count": 1,
                    "created": now,
                    "updated": now,
                })
            else:
                if content not in target["steps"]:
                    target["steps"].append(content)

                target["steps"] = target["steps"][-20:]
                target["success_count"] = (
                    int(target.get("success_count", 0)) + 1
                )
                target["updated"] = now

    _update_memory(update)

    return {
        "success": True,
        "data": {
            "kind": kind,
            "key": key,
            "content": content,
        },
        "output": "Память сохранена.",
    }


def recall_memory(query: str, limit: int = 8):
    """Retrieve the most relevant durable memories."""

    query = str(query or "").strip()

    if not query:
        return {
            "success": False,
            "error": "empty_query",
            "output": "Не указан запрос для поиска памяти.",
        }

    limit = max(1, min(int(limit or 8), 20))
    memory = load_memory()

    candidates = []

    for item in memory["facts"]:
        text = (
            str(item.get("key", ""))
            + " "
            + str(item.get("value", ""))
        )

        score = _memory_score(
            query,
            text,
            item.get("confidence", 0.0),
        )

        if score > 0:
            candidates.append((
                score,
                "fact",
                item,
            ))

    for item in memory["preferences"]:
        text = (
            str(item.get("key", ""))
            + " "
            + str(item.get("value", ""))
        )

        score = _memory_score(
            query,
            text,
            item.get("confidence", 0.0),
        )

        if score > 0:
            candidates.append((
                score,
                "preference",
                item,
            ))

    for item in memory["episodes"]:
        text = (
            str(item.get("summary", ""))
            + " "
            + str(item.get("context", ""))
            + " "
            + " ".join(item.get("tags", []))
        )

        score = _memory_score(
            query,
            text,
            item.get("importance", 0.0),
        )

        if score > 0:
            candidates.append((
                score,
                "episode",
                item,
            ))

    for item in memory["procedures"]:
        text = (
            str(item.get("name", ""))
            + " "
            + " ".join(str(step) for step in item.get("steps", []))
        )

        score = _memory_score(
            query,
            text,
            min(
                float(item.get("success_count", 0)) / 10.0,
                1.0,
            ),
        )

        if score > 0:
            candidates.append((
                score,
                "procedure",
                item,
            ))

    # Existing goal/task/event memory remains searchable too.
    for item in memory["goals"]:
        text = str(item.get("text", ""))

        score = _memory_score(query, text, 0.5)

        if score > 0:
            candidates.append((
                score,
                "goal",
                item,
            ))

    for item in memory["tasks"]:
        text = (
            str(item.get("text", ""))
            + " "
            + str(item.get("goal", ""))
        )

        score = _memory_score(
            query,
            text,
            0.5 if not item.get("completed") else 0.1,
        )

        if score > 0:
            candidates.append((
                score,
                "task",
                item,
            ))

    candidates.sort(
        key=lambda item: -item[0]
    )

    selected = candidates[:limit]

    result = []

    for score, kind, item in selected:
        result.append({
            "kind": kind,
            "score": round(score, 3),
            "memory": item,
        })

    if not result:
        return {
            "success": True,
            "data": {
                "query": query,
                "results": [],
            },
            "output": "Релевантной сохранённой памяти не найдено.",
        }

    lines = []

    for item in result:
        memory_item = item["memory"]
        kind = item["kind"]

        if kind in {"fact", "preference"}:
            lines.append(
                f"[{kind}] "
                f"{memory_item.get('key')}: "
                f"{memory_item.get('value')}"
            )

        elif kind == "episode":
            lines.append(
                "[episode] "
                + str(memory_item.get("summary", ""))
            )

        elif kind == "procedure":
            lines.append(
                "[procedure] "
                + str(memory_item.get("name", ""))
                + ": "
                + " → ".join(
                    str(step)
                    for step in memory_item.get("steps", [])
                )
            )

        elif kind == "goal":
            lines.append(
                "[goal] "
                + str(memory_item.get("text", ""))
            )

        elif kind == "task":
            lines.append(
                "[task] "
                + str(memory_item.get("text", ""))
            )

    return {
        "success": True,
        "data": {
            "query": query,
            "results": result,
        },
        "output": "\n".join(lines),
    }


def build_memory_context(query: str, limit: int = 6) -> str:
    """Build a compact memory block for reasoning context.

    This is intentionally read-only and never mutates memory.
    """

    result = recall_memory(query, limit)

    if not result.get("success"):
        return ""

    data = result.get("data") or {}
    results = data.get("results") or []

    if not results:
        return ""

    lines = [
        "[RELEVANT LONG-TERM MEMORY]",
    ]

    for item in results:
        kind = item["kind"]
        memory_item = item["memory"]

        if kind in {"fact", "preference"}:
            lines.append(
                f"- {kind}: "
                f"{memory_item.get('key')} = "
                f"{memory_item.get('value')}"
            )

        elif kind == "episode":
            lines.append(
                "- episode: "
                + str(memory_item.get("summary", ""))
            )

        elif kind == "procedure":
            lines.append(
                "- procedure: "
                + str(memory_item.get("name", ""))
                + " | "
                + " → ".join(
                    str(step)
                    for step in memory_item.get("steps", [])
                )
            )

        elif kind == "goal":
            lines.append(
                "- goal: "
                + str(memory_item.get("text", ""))
            )

        elif kind == "task":
            lines.append(
                "- task: "
                + str(memory_item.get("text", ""))
            )

    lines.append(
        "[END RELEVANT LONG-TERM MEMORY]"
    )

    return "\n".join(lines)


# === AKIRA MEMORY 2.0 NORMALIZATION OVERRIDE ===
#
# This definition intentionally lives at the end of the module.
# Existing load_memory() resolves _normalize_memory at runtime,
# therefore the override safely upgrades legacy memory files
# without rewriting the existing Memory 2.0 implementation.

def _normalize_memory(data):
    """Normalize legacy and Memory 2.0 memory without data loss."""

    memory = data.copy() if isinstance(data, dict) else {}

    # --------------------------------------------------------
    # Legacy collections
    # --------------------------------------------------------

    for field in (
        "goals",
        "tasks",
        "events",
        "activity",
    ):
        if not isinstance(memory.get(field), list):
            memory[field] = []

    memory["goals"] = [
        {
            "text": "",
            "created": "",
            **item,
        }
        for item in memory["goals"]
        if isinstance(item, dict)
    ]

    memory["tasks"] = [
        {
            "text": "",
            "goal": None,
            "completed": False,
            "created": "",
            **item,
        }
        for item in memory["tasks"]
        if isinstance(item, dict)
    ]

    memory["events"] = [
        {
            "text": "",
            "time": "",
            **item,
        }
        for item in memory["events"]
        if isinstance(item, dict)
    ]

    memory["activity"] = [
        {
            "app": "Неизвестно",
            "started": "",
            "ended": "",
            "duration_seconds": 0,
            **item,
        }
        for item in memory["activity"]
        if isinstance(item, dict)
    ]

    # --------------------------------------------------------
    # Memory 2.0 collections
    # --------------------------------------------------------

    for field in (
        "facts",
        "preferences",
        "episodes",
        "procedures",
    ):
        if not isinstance(memory.get(field), list):
            memory[field] = []

    memory["facts"] = [
        {
            "key": "",
            "value": "",
            "category": "fact",
            "source": "unknown",
            "confidence": 1.0,
            "created": "",
            "updated": "",
            **item,
        }
        for item in memory["facts"]
        if isinstance(item, dict)
    ]

    memory["preferences"] = [
        {
            "key": "",
            "value": "",
            "source": "unknown",
            "confidence": 1.0,
            "created": "",
            "updated": "",
            **item,
        }
        for item in memory["preferences"]
        if isinstance(item, dict)
    ]

    memory["episodes"] = [
        {
            "summary": "",
            "context": "",
            "importance": 0.5,
            "tags": [],
            "created": "",
            **item,
        }
        for item in memory["episodes"]
        if isinstance(item, dict)
    ]

    memory["procedures"] = [
        {
            "name": "",
            "steps": [],
            "success_count": 0,
            "created": "",
            "updated": "",
            **item,
        }
        for item in memory["procedures"]
        if isinstance(item, dict)
    ]

    return memory
