
"""Desktop awareness runtime for Akira.

Awareness is deliberately separate from vision reasoning.

It periodically samples cheap local desktop state:

    screenshot metadata
    frontmost application
    screen dimensions

and emits ``desktop.changed`` only when the observable state changes.

The screenshot itself is NOT automatically sent to an LLM.

This gives Akira an always-on sensory layer without turning every
heartbeat into an expensive vision request.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

STATE_FILE = (
    ROOT
    / "runtime"
    / "awareness_state.json"
)


class AwarenessRuntime:
    """Persistent desktop state observer."""

    def __init__(
        self,
        enabled=True,
    ):
        self.enabled = bool(enabled)

        self._lock = threading.RLock()

        self._last_fingerprint = None
        self._last_state = None
        self._sample_count = 0
        self._change_count = 0
        self._last_sample = None
        self._last_change = None

        self._load()

    # ========================================================
    # Persistence
    # ========================================================

    def _load(self):
        STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not STATE_FILE.exists():
            return

        try:
            data = json.loads(
                STATE_FILE.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return

        if not isinstance(data, dict):
            return

        self._last_fingerprint = data.get(
            "last_fingerprint"
        )

        self._last_state = data.get(
            "last_state"
        )

        self._sample_count = int(
            data.get(
                "sample_count",
                0,
            )
        )

        self._change_count = int(
            data.get(
                "change_count",
                0,
            )
        )

        self._last_sample = data.get(
            "last_sample"
        )

        self._last_change = data.get(
            "last_change"
        )

    def _save(self):
        STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = {
            "enabled": self.enabled,
            "last_fingerprint": self._last_fingerprint,
            "last_state": self._last_state,
            "sample_count": self._sample_count,
            "change_count": self._change_count,
            "last_sample": self._last_sample,
            "last_change": self._last_change,
        }

        temporary = STATE_FILE.with_suffix(
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
            STATE_FILE
        )

    # ========================================================
    # Sampling
    # ========================================================

    def sample(self):
        """Capture cheap desktop state and detect changes."""

        with self._lock:

            if not self.enabled:
                return {
                    "success": True,
                    "enabled": False,
                    "changed": False,
                    "output": (
                        "Desktop awareness отключён."
                    ),
                }

        try:
            from capabilities.observe import (
                capture_screenshot,
                screen_size,
                ui_metadata,
            )

            screenshot_path, error = (
                capture_screenshot()
            )

            if error:
                return {
                    "success": False,
                    "error": "screenshot_error",
                    "changed": False,
                    "output": str(error),
                }

            size_result = screen_size()

            screen = (
                size_result.get("data")
                if size_result.get("success")
                else None
            )

            ui = ui_metadata()

            state = {
                "screen": screen,
                "ui": ui,
                "screenshot_path": screenshot_path,
            }

        except Exception as error:

            return {
                "success": False,
                "error": "awareness_sample_error",
                "changed": False,
                "output": str(error),
            }

        # Do not fingerprint volatile screenshot filename.
        fingerprint_state = {
            "screen": screen,
            "ui": ui,
        }

        encoded = json.dumps(
            fingerprint_state,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode(
            "utf-8"
        )

        fingerprint = hashlib.sha256(
            encoded
        ).hexdigest()

        now = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )

        with self._lock:

            previous = self._last_fingerprint

            changed = (
                previous is not None
                and previous != fingerprint
            )

            first_sample = (
                previous is None
            )

            self._last_fingerprint = fingerprint
            self._last_state = state
            self._sample_count += 1
            self._last_sample = now

            if changed:
                self._change_count += 1
                self._last_change = now

            self._save()

        # First observation establishes baseline.
        if first_sample:
            return {
                "success": True,
                "enabled": True,
                "changed": False,
                "baseline": True,
                "state": state,
                "output": (
                    "Desktop awareness baseline established."
                ),
            }

        if changed:
            event_result = None

            try:
                from event_bus import emit_event

                event_result = emit_event(
                    "desktop.changed",
                    {
                        "screen": screen,
                        "ui": ui,
                        "screenshot_path": screenshot_path,
                        "timestamp": now,
                    },
                )

            except Exception as error:
                event_result = {
                    "success": False,
                    "error": str(error),
                }

            return {
                "success": True,
                "enabled": True,
                "changed": True,
                "state": state,
                "event": event_result,
                "output": (
                    "Desktop state changed."
                ),
            }

        return {
            "success": True,
            "enabled": True,
            "changed": False,
            "state": state,
            "output": (
                "Desktop state unchanged."
            ),
        }

    # ========================================================
    # State
    # ========================================================

    def state(self):
        with self._lock:

            return {
                "success": True,
                "enabled": self.enabled,
                "last_state": self._last_state,
                "sample_count": self._sample_count,
                "change_count": self._change_count,
                "last_sample": self._last_sample,
                "last_change": self._last_change,
                "output": json.dumps(
                    {
                        "enabled": self.enabled,
                        "last_state": self._last_state,
                        "sample_count": self._sample_count,
                        "change_count": self._change_count,
                        "last_sample": self._last_sample,
                        "last_change": self._last_change,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }

    # ========================================================
    # Privacy
    # ========================================================

    def set_enabled(self, enabled):
        with self._lock:

            self.enabled = bool(
                enabled
            )

            self._save()

        return {
            "success": True,
            "enabled": self.enabled,
            "output": (
                "Desktop awareness "
                + (
                    "включён."
                    if self.enabled
                    else "отключён."
                )
            ),
        }


_awareness = None
_awareness_lock = threading.Lock()


def get_awareness():
    global _awareness

    if _awareness is None:

        with _awareness_lock:

            if _awareness is None:
                _awareness = AwarenessRuntime()

    return _awareness


def awareness_sample():
    return get_awareness().sample()


def awareness_state():
    return get_awareness().state()


def awareness_enabled(enabled):
    return get_awareness().set_enabled(
        enabled
    )
