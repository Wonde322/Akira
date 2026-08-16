
"""Persistent event bus and trigger runtime for Akira.

An event is data:

    {
        "type": "task.completed",
        "payload": {...}
    }

A trigger is a persistent rule:

    event type
        ->
    natural-language goal
        ->
    TaskRuntime

The event bus itself never executes arbitrary Python.
All resulting work enters the normal Akira execution path.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

RUNTIME_DIR = ROOT / "runtime"

EVENT_LOG = RUNTIME_DIR / "events.jsonl"
TRIGGER_FILE = RUNTIME_DIR / "triggers.json"

MAX_TRIGGERS = 200
MAX_EVENT_LOG_BYTES = 2_000_000


def _now():
    return datetime.now().astimezone()


def _iso(value=None):
    value = value or _now()

    return value.isoformat(
        timespec="seconds"
    )


class EventBus:
    """Persistent trigger/event dispatcher."""

    def __init__(self):
        self._lock = threading.RLock()
        self._triggers = {}

        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._load_triggers()

    # ========================================================
    # Persistence
    # ========================================================

    def _load_triggers(self):
        if not TRIGGER_FILE.exists():
            return

        try:
            data = json.loads(
                TRIGGER_FILE.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return

        if not isinstance(data, list):
            return

        for trigger in data[-MAX_TRIGGERS:]:
            if not isinstance(trigger, dict):
                continue

            trigger_id = trigger.get("id")

            if trigger_id:
                self._triggers[trigger_id] = trigger

    def _save_triggers(self):
        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = list(
            self._triggers.values()
        )[-MAX_TRIGGERS:]

        tmp = TRIGGER_FILE.with_suffix(
            ".json.tmp"
        )

        tmp.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(
            TRIGGER_FILE
        )

    def _append_event(self, event):
        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        if EVENT_LOG.exists():
            try:
                if EVENT_LOG.stat().st_size > MAX_EVENT_LOG_BYTES:
                    old = EVENT_LOG.read_text(
                        encoding="utf-8"
                    ).splitlines()

                    keep = old[-1000:]

                    EVENT_LOG.write_text(
                        "\n".join(keep) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass

        with EVENT_LOG.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    event,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    # ========================================================
    # Trigger management
    # ========================================================

    def create_trigger(
        self,
        event_type,
        goal,
        cooldown_seconds=0,
    ):
        event_type = str(
            event_type or ""
        ).strip()

        goal = str(
            goal or ""
        ).strip()

        if not event_type:
            return {
                "success": False,
                "error": "empty_event_type",
                "output": "Не указан event_type.",
            }

        if not goal:
            return {
                "success": False,
                "error": "empty_goal",
                "output": "Не указана trigger goal.",
            }

        try:
            cooldown = max(
                0,
                int(cooldown_seconds or 0),
            )
        except Exception:
            return {
                "success": False,
                "error": "invalid_cooldown",
                "output": "cooldown_seconds должен быть числом.",
            }

        trigger_id = uuid.uuid4().hex[:12]

        trigger = {
            "id": trigger_id,
            "event_type": event_type,
            "goal": goal,
            "enabled": True,
            "cooldown_seconds": cooldown,
            "created_at": _iso(),
            "last_fired_at": None,
            "fire_count": 0,
            "last_task_id": None,
            "last_error": None,
        }

        with self._lock:
            self._triggers[trigger_id] = trigger
            self._save_triggers()

        return {
            "success": True,
            "trigger_id": trigger_id,
            "trigger": dict(trigger),
            "output": (
                f"Trigger {trigger_id} создан."
            ),
        }

    def cancel_trigger(self, trigger_id):
        trigger_id = str(
            trigger_id or ""
        )

        with self._lock:
            trigger = self._triggers.get(
                trigger_id
            )

            if trigger is None:
                return {
                    "success": False,
                    "error": "trigger_not_found",
                    "output": (
                        f"Trigger {trigger_id} не найден."
                    ),
                }

            trigger["enabled"] = False
            trigger["cancelled_at"] = _iso()

            self._save_triggers()

        return {
            "success": True,
            "trigger_id": trigger_id,
            "output": (
                f"Trigger {trigger_id} отключён."
            ),
        }

    def list_triggers(self, limit=100):
        try:
            limit = int(limit)
        except Exception:
            limit = 100

        limit = max(
            1,
            min(limit, 100),
        )

        with self._lock:
            data = list(
                self._triggers.values()
            )[-limit:]

            data.reverse()

        return {
            "success": True,
            "triggers": data,
            "output": json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
        }

    # ========================================================
    # Event emission
    # ========================================================

    def emit(
        self,
        event_type,
        payload=None,
    ):
        event = {
            "id": uuid.uuid4().hex[:16],
            "type": str(event_type),
            "timestamp": _iso(),
            "payload": (
                payload
                if isinstance(payload, dict)
                else {}
            ),
        }

        with self._lock:
            self._append_event(event)

            triggers = [
                dict(trigger)
                for trigger in self._triggers.values()
                if (
                    trigger.get("enabled")
                    and trigger.get("event_type")
                    == event["type"]
                )
            ]

        launched = []

        if not triggers:
            return {
                "success": True,
                "event": event,
                "launched": [],
                "output": "Event emitted; no triggers matched.",
            }

        # Execution is deliberately lazy-imported.
        from task_runtime import get_runtime

        runtime = get_runtime()

        for trigger in triggers:

            if self._cooldown_active(
                trigger
            ):
                continue

            goal = self._render_goal(
                trigger.get("goal", ""),
                event,
            )

            result = runtime.spawn(
                goal,
                session_id=(
                    f"trigger:{trigger['id']}"
                ),
            )

            with self._lock:
                current = self._triggers.get(
                    trigger["id"]
                )

                if current is None:
                    continue

                if result.get("success"):
                    current["last_fired_at"] = (
                        _iso()
                    )

                    current["fire_count"] = (
                        int(
                            current.get(
                                "fire_count"
                            )
                            or 0
                        )
                        + 1
                    )

                    current["last_task_id"] = (
                        result.get(
                            "task_id"
                        )
                    )

                    current["last_error"] = None

                    launched.append(
                        {
                            "trigger_id": trigger["id"],
                            "task_id": result.get(
                                "task_id"
                            ),
                        }
                    )

                else:
                    current["last_error"] = (
                        result.get("error")
                        or result.get("output")
                    )

                self._save_triggers()

        return {
            "success": True,
            "event": event,
            "launched": launched,
            "output": json.dumps(
                launched,
                ensure_ascii=False,
            ),
        }

    # ========================================================
    # Cooldown
    # ========================================================

    def _cooldown_active(self, trigger):
        cooldown = int(
            trigger.get(
                "cooldown_seconds"
            )
            or 0
        )

        if cooldown <= 0:
            return False

        last = trigger.get(
            "last_fired_at"
        )

        if not last:
            return False

        try:
            timestamp = datetime.fromisoformat(
                last
            )
        except Exception:
            return False

        elapsed = (
            _now() - timestamp
        ).total_seconds()

        return elapsed < cooldown

    # ========================================================
    # Goal templating
    # ========================================================

    def _render_goal(
        self,
        goal,
        event,
    ):
        payload = event.get(
            "payload",
            {},
        )

        result = str(goal)

        replacements = {
            "{{event.type}}": str(
                event.get("type", "")
            ),
            "{{event.id}}": str(
                event.get("id", "")
            ),
            "{{event.timestamp}}": str(
                event.get("timestamp", "")
            ),
            "{{event.payload}}": json.dumps(
                payload,
                ensure_ascii=False,
            ),
        }

        for key, value in replacements.items():
            result = result.replace(
                key,
                value,
            )

        return result


_bus = None
_bus_lock = threading.Lock()


def get_event_bus():
    global _bus

    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()

    return _bus


def create_trigger(
    event_type,
    goal,
    cooldown_seconds=0,
):
    return get_event_bus().create_trigger(
        event_type,
        goal,
        cooldown_seconds,
    )


def cancel_trigger(
    trigger_id,
):
    return get_event_bus().cancel_trigger(
        trigger_id
    )


def list_triggers(
    limit=100,
):
    return get_event_bus().list_triggers(
        limit
    )


def emit_event(
    event_type,
    payload=None,
):
    return get_event_bus().emit(
        event_type,
        payload,
    )
