"""Persistent goals and priority-aware context matching for proactive Akira."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOALS_FILE = ROOT / "runtime" / "proactive_goals.json"
PRIORITY_WEIGHTS = {"low": 0.25, "normal": 0.5, "high": 0.75, "critical": 1.0}
_TERMINAL = {"completed", "cancelled", "failed", "archived"}
_STOP = {"и", "в", "во", "на", "с", "со", "для", "по", "к", "из", "the", "a", "an", "to", "of", "for", "and", "with", "in", "on"}


def _tokens(value):
    return {t.lower() for t in re.findall(r"[\w-]+", str(value or ""), flags=re.UNICODE) if len(t) >= 3 and t.lower() not in _STOP}


def _parse_deadline(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


class GoalStore:
    """Small persistent store intentionally limited to explicit user/Akira goals."""

    def __init__(self, path=None):
        self.path = Path(path) if path else GOALS_FILE
        self._lock = threading.RLock()
        self._goals = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, list):
            self._goals = {str(item.get("id")): dict(item) for item in data if isinstance(item, dict) and item.get("id")}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(list(self._goals.values()), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def create(self, title, priority="normal", deadline=None, status="active", task_id=None):
        title = str(title or "").strip()
        if not title:
            return {"success": False, "error": "empty_goal"}
        priority = str(priority or "normal").lower()
        if priority not in PRIORITY_WEIGHTS:
            return {"success": False, "error": "invalid_priority"}
        if deadline is not None and _parse_deadline(deadline) is None:
            return {"success": False, "error": "invalid_deadline"}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        goal = {"id": uuid.uuid4().hex[:12], "title": title, "priority": priority, "deadline": deadline,
                "status": status, "task_id": task_id, "created_at": now, "updated_at": now}
        with self._lock:
            self._goals[goal["id"]] = goal
            self._save()
        return {"success": True, "goal": dict(goal)}

    def list(self, include_terminal=False):
        with self._lock:
            goals = [dict(g) for g in self._goals.values() if include_terminal or str(g.get("status")) not in _TERMINAL]
        return sorted(goals, key=lambda g: (PRIORITY_WEIGHTS.get(g.get("priority"), 0), g.get("created_at", "")), reverse=True)

    def update(self, goal_id, **changes):
        with self._lock:
            goal = self._goals.get(str(goal_id))
            if not goal:
                return {"success": False, "error": "goal_not_found"}
            if "priority" in changes:
                priority = str(changes["priority"]).lower()
                if priority not in PRIORITY_WEIGHTS:
                    return {"success": False, "error": "invalid_priority"}
                goal["priority"] = priority
            if "deadline" in changes and changes["deadline"] is not None and _parse_deadline(changes["deadline"]) is None:
                return {"success": False, "error": "invalid_deadline"}
            for key in ("title", "deadline", "status", "task_id"):
                if key in changes:
                    goal[key] = changes[key]
            goal["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._save()
            return {"success": True, "goal": dict(goal)}


class GoalContextLinker:
    """Connect desktop context/active tasks to explicit goals and urgency."""

    def __init__(self, store=None, now=None):
        self.store = store or get_goal_store()
        self._now = now

    def _urgency(self, goal):
        base = PRIORITY_WEIGHTS.get(goal.get("priority"), 0.5)
        deadline = _parse_deadline(goal.get("deadline"))
        if deadline is None:
            return round(base, 3)
        now = self._now or datetime.now(timezone.utc)
        hours = (deadline - now).total_seconds() / 3600
        if hours <= 0:
            return 1.0
        if hours <= 6:
            return round(max(base, 0.95), 3)
        if hours <= 24:
            return round(max(base, 0.85), 3)
        if hours <= 72:
            return round(max(base, 0.7), 3)
        return round(base, 3)

    @staticmethod
    def _score(goal, context, active_task):
        haystack = " ".join([str((context or {}).get("app") or ""), str((context or {}).get("title") or ""), str((active_task or {}).get("goal") or "")])
        left, right = _tokens(goal.get("title")), _tokens(haystack)
        if not left or not right:
            return 0.0
        overlap = left & right
        score = len(overlap) / max(1, min(len(left), len(right)))
        if active_task and goal.get("task_id") and str(goal.get("task_id")) == str(active_task.get("task_id")):
            score = max(score, 1.0)
        return round(score, 3)

    def match(self, context, active_task=None):
        candidates = []
        for goal in self.store.list():
            score = self._score(goal, context, active_task)
            if score > 0:
                candidates.append((score, self._urgency(goal), goal))
        if not candidates:
            return None
        confidence, urgency, goal = max(candidates, key=lambda item: (item[0] * 0.7 + item[1] * 0.3, item[1]))
        return {"goal_id": goal["id"], "title": goal["title"], "priority": goal["priority"], "deadline": goal.get("deadline"),
                "confidence": confidence, "urgency": urgency, "task_id": goal.get("task_id")}

_goal_store = None
_goal_lock = threading.Lock()

def get_goal_store():
    global _goal_store
    if _goal_store is None:
        with _goal_lock:
            if _goal_store is None:
                _goal_store = GoalStore()
    return _goal_store

def create_goal(title, priority="normal", deadline=None, task_id=None):
    return get_goal_store().create(title, priority=priority, deadline=deadline, task_id=task_id)

def list_goals(include_terminal=False):
    return get_goal_store().list(include_terminal=include_terminal)
