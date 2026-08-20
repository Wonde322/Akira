"""Explicit user-feedback memory for proactive interventions.

Only deliberate proposal choices are learned from. The component never infers
sentiment from ambient desktop activity, so proactive adaptation stays bounded
and inspectable.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone


class ProactiveFeedbackStore:
    def __init__(self, path="runtime/proactive_feedback.json", suppress_after=3):
        self.path = path
        self.suppress_after = max(1, int(suppress_after))
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.path)

    @staticmethod
    def _reason(reason):
        return str(reason or "").strip() or "unknown"

    def record(self, reason, proposal_kind):
        reason = self._reason(reason)
        kind = str(proposal_kind or "").strip()
        outcome = "dismissed" if kind == "dismiss" else "accepted"
        with self._lock:
            item = dict(self._data.get(reason) or {})
            item["accepted"] = int(item.get("accepted") or 0) + (outcome == "accepted")
            item["dismissed"] = int(item.get("dismissed") or 0) + (outcome == "dismissed")
            item["last_outcome"] = outcome
            item["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._data[reason] = item
            self._save()
            return {"reason": reason, **item}

    def stats(self, reason):
        reason = self._reason(reason)
        with self._lock:
            item = dict(self._data.get(reason) or {})
        return {"reason": reason, "accepted": int(item.get("accepted") or 0),
                "dismissed": int(item.get("dismissed") or 0),
                "last_outcome": item.get("last_outcome"), "updated_at": item.get("updated_at")}

    def should_suppress_question(self, reason):
        stats = self.stats(reason)
        return stats["dismissed"] >= self.suppress_after and stats["dismissed"] > stats["accepted"]

    def snapshot(self):
        with self._lock:
            return {key: self.stats(key) for key in sorted(self._data)}


_store = None
_store_lock = threading.Lock()


def get_proactive_feedback_store():
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ProactiveFeedbackStore()
    return _store
