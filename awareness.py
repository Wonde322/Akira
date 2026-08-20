"""Desktop awareness runtime for Akira."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "runtime" / "awareness_state.json"


class AwarenessRuntime:
    def __init__(self, enabled=True, pattern_engine=None, task_context_linker=None):
        self.enabled = bool(enabled)
        self._lock = threading.RLock()
        self._last_fingerprint = None
        self._last_state = None
        self._sample_count = 0
        self._change_count = 0
        self._last_sample = None
        self._last_change = None
        if pattern_engine is None:
            from context_patterns import get_context_pattern_engine
            pattern_engine = get_context_pattern_engine()
        self._pattern_engine = pattern_engine
        if task_context_linker is None:
            from task_context import TaskContextLinker
            task_context_linker = TaskContextLinker()
        self._task_context_linker = task_context_linker
        self._load()

    def _load(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not STATE_FILE.exists(): return
        try: data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception: return
        if not isinstance(data, dict): return
        self._last_fingerprint = data.get("last_fingerprint")
        self._last_state = data.get("last_state")
        self._sample_count = int(data.get("sample_count", 0))
        self._change_count = int(data.get("change_count", 0))
        self._last_sample = data.get("last_sample")
        self._last_change = data.get("last_change")

    def _save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"enabled": self.enabled, "last_fingerprint": self._last_fingerprint,
                "last_state": self._last_state, "sample_count": self._sample_count,
                "change_count": self._change_count, "last_sample": self._last_sample,
                "last_change": self._last_change}
        temporary = STATE_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(STATE_FILE)

    @staticmethod
    def _changed_fields(previous, current):
        previous = previous if isinstance(previous, dict) else {}
        current = current if isinstance(current, dict) else {}
        return [field for field in ("screen", "ui") if previous.get(field) != current.get(field)]

    def _enrich_pattern(self, insight):
        item = dict(insight)
        context = item.get("context") or {}
        try:
            active_task = self._task_context_linker.match(context)
        except Exception:
            active_task = None
        if active_task is not None:
            item["active_task"] = active_task
        return item

    @staticmethod
    def _emit_patterns(insights, timestamp):
        results = []
        if not insights: return results
        try: from event_bus import emit_event
        except Exception as error: return [{"success": False, "error": str(error)}]
        for insight in insights:
            payload = {key: value for key, value in insight.items() if key != "type"}
            payload["timestamp"] = timestamp
            try: results.append(emit_event(insight["type"], payload, source="awareness.pattern"))
            except Exception as error: results.append({"success": False, "error": str(error)})
        return results

    def sample(self):
        with self._lock:
            if not self.enabled:
                return {"success": True, "enabled": False, "changed": False, "patterns": [], "output": "Desktop awareness отключён."}
        try:
            from capabilities.observe import capture_screenshot, screen_size, ui_metadata
            screenshot_path, error = capture_screenshot()
            if error:
                return {"success": False, "error": "screenshot_error", "changed": False, "patterns": [], "output": str(error)}
            size_result = screen_size()
            screen = size_result.get("data") if size_result.get("success") else None
            ui = ui_metadata()
            state = {"screen": screen, "ui": ui, "screenshot_path": screenshot_path}
        except Exception as error:
            return {"success": False, "error": "awareness_sample_error", "changed": False, "patterns": [], "output": str(error)}
        fingerprint_state = {"screen": screen, "ui": ui}
        encoded = json.dumps(fingerprint_state, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        try: insights = [self._enrich_pattern(item) for item in self._pattern_engine.observe(ui)]
        except Exception: insights = []
        pattern_events = self._emit_patterns(insights, now)
        with self._lock:
            previous_fingerprint = self._last_fingerprint; previous_state = self._last_state
            changed = previous_fingerprint is not None and previous_fingerprint != fingerprint
            first_sample = previous_fingerprint is None
            changed_fields = self._changed_fields(previous_state, state) if changed else []
            self._last_fingerprint = fingerprint; self._last_state = state; self._sample_count += 1; self._last_sample = now
            if changed: self._change_count += 1; self._last_change = now
            self._save()
        if first_sample:
            return {"success": True, "enabled": True, "changed": False, "baseline": True, "patterns": insights, "pattern_events": pattern_events, "state": state, "output": "Desktop awareness baseline established."}
        if changed:
            event_result = None
            try:
                from event_bus import emit_event
                event_result = emit_event("desktop.changed", {"screen": screen, "ui": ui, "previous_ui": (previous_state or {}).get("ui"), "changed_fields": changed_fields, "screenshot_path": screenshot_path, "timestamp": now}, source="awareness")
            except Exception as error: event_result = {"success": False, "error": str(error)}
            return {"success": True, "enabled": True, "changed": True, "changed_fields": changed_fields, "patterns": insights, "pattern_events": pattern_events, "state": state, "event": event_result, "output": "Desktop state changed."}
        return {"success": True, "enabled": True, "changed": False, "patterns": insights, "pattern_events": pattern_events, "state": state, "output": "Desktop state unchanged."}

    def state(self):
        with self._lock:
            data = {"enabled": self.enabled, "last_state": self._last_state, "sample_count": self._sample_count, "change_count": self._change_count, "last_sample": self._last_sample, "last_change": self._last_change}
        return {"success": True, **data, "output": json.dumps(data, ensure_ascii=False, indent=2)}

    def set_enabled(self, enabled):
        with self._lock: self.enabled = bool(enabled); self._save()
        return {"success": True, "enabled": self.enabled, "output": "Desktop awareness " + ("включён." if self.enabled else "отключён.")}

_awareness = None
_awareness_lock = threading.Lock()

def get_awareness():
    global _awareness
    if _awareness is None:
        with _awareness_lock:
            if _awareness is None: _awareness = AwarenessRuntime()
    return _awareness

def awareness_sample(): return get_awareness().sample()
def awareness_state(): return get_awareness().state()
def awareness_enabled(enabled): return get_awareness().set_enabled(enabled)
