"""End-to-end scenario runner for Akira's proactive pipeline.

The runner is intentionally thin: production decisions remain in EventBus and
ProactiveRuntime.  This module provides one place to drive a correlated sequence
of events and inspect the decisions made at every stage.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProactiveScenario:
    id: str
    steps: list[dict[str, Any]] = field(default_factory=list)


class ProactiveScenarioRunner:
    def __init__(self, emit=None):
        if emit is None:
            from event_bus import emit_event
            emit = emit_event
        self._emit = emit

    def run(self, steps, scenario_id=None):
        scenario_id = str(scenario_id or uuid.uuid4().hex)
        trace = ProactiveScenario(scenario_id)
        parent_event_id = None
        for index, raw in enumerate(list(steps or [])):
            if not isinstance(raw, dict):
                raise ValueError("scenario_step_must_be_mapping")
            event_type = str(raw.get("type") or "").strip()
            if not event_type:
                raise ValueError("scenario_step_requires_type")
            payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
            metadata = dict(raw.get("metadata") or {})
            metadata.setdefault("correlation_id", scenario_id)
            metadata.setdefault("parent_event_id", parent_event_id)
            metadata.setdefault("causation_depth", 0 if parent_event_id is None else 1)
            metadata.setdefault("source", "proactive.e2e")
            result = self._emit(event_type, payload, **metadata)
            event = result.get("event") if isinstance(result, dict) else None
            if isinstance(event, dict) and event.get("id"):
                parent_event_id = event["id"]
            trace.steps.append({
                "index": index,
                "input": {"type": event_type, "payload": payload},
                "result": result,
                "decision": (result or {}).get("decision") if isinstance(result, dict) else None,
            })
        return {
            "success": all((step["result"] or {}).get("success", False) for step in trace.steps if isinstance(step["result"], dict)),
            "scenario_id": trace.id,
            "steps": trace.steps,
        }


def run_proactive_scenario(steps, scenario_id=None):
    return ProactiveScenarioRunner().run(steps, scenario_id=scenario_id)
