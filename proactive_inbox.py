"""Persistent inbox for proactive Akira events.

The proactive runtime may decide that something deserves the user's
attention even when there is no desktop notification surface available.
This module stores those items durably so the UI/voice layer can consume
and acknowledge them later.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBOX_FILE = ROOT / "runtime" / "proactive_inbox.json"
MAX_ITEMS = 200


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ProactiveInbox:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else INBOX_FILE
        self._lock = threading.RLock()
        self._items = []
        self._load()

    def _load(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, list):
            self._items = [item for item in data[-MAX_ITEMS:] if isinstance(item, dict)]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._items[-MAX_ITEMS:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def push(self, message, *, action="notify", event=None, priority="normal", reason=None):
        item = {
            "id": uuid.uuid4().hex[:12],
            "created_at": _now_iso(),
            "action": str(action),
            "message": str(message or ""),
            "priority": str(priority or "normal"),
            "reason": reason,
            "event_id": (event or {}).get("id"),
            "event_type": (event or {}).get("type"),
            "read": False,
            "read_at": None,
        }
        with self._lock:
            self._items.append(item)
            del self._items[:-MAX_ITEMS]
            self._save()
        return dict(item)

    def list(self, limit=20, unread_only=False):
        try:
            limit = int(limit)
        except Exception:
            limit = 20
        limit = max(1, min(limit, 100))
        with self._lock:
            items = self._items
            if unread_only:
                items = [item for item in items if not item.get("read")]
            return [dict(item) for item in items[-limit:]][::-1]

    def acknowledge(self, item_id):
        with self._lock:
            for item in self._items:
                if item.get("id") == str(item_id):
                    if not item.get("read"):
                        item["read"] = True
                        item["read_at"] = _now_iso()
                        self._save()
                    return {"success": True, "item": dict(item)}
        return {"success": False, "error": "inbox_item_not_found"}


_inbox = None
_inbox_lock = threading.Lock()


def get_proactive_inbox():
    global _inbox
    if _inbox is None:
        with _inbox_lock:
            if _inbox is None:
                _inbox = ProactiveInbox()
    return _inbox


def proactive_inbox(limit=20, unread_only=False):
    return {
        "success": True,
        "items": get_proactive_inbox().list(limit, unread_only),
    }


def acknowledge_proactive(item_id):
    return get_proactive_inbox().acknowledge(item_id)
