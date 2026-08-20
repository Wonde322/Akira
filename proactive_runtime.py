"""Event-driven proactive runtime for Akira."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum

from context_triggers import ContextTriggerEngine
from proactive_policy import get_proactive_reasoning_policy
from proactive_action_proposals import get_proactive_action_proposer
from proactive_attention_budget import get_proactive_attention_budget
from proactive_orchestrator import get_proactive_orchestrator

MAX_CAUSATION_DEPTH = 3
MAX_COMPLETION_RESULT_CHARS = 1200


class ProactiveAction(str, Enum):
    IGNORE = "ignore"
    RECORD = "record"
    NOTIFY = "notify"
    SPAWN_TASK = "spawn_task"
    ASK_USER = "ask_user"


@dataclass
class ProactiveDecision:
    action: ProactiveAction
    reason: str
    goal: str | None = None
    notification: str | None = None
    source: str = "policy"
    priority: str = "normal"
    proposals: list | None = None
    source_task_id: str | None = None

    def to_dict(self):
        data = asdict(self)
        data["action"] = self.action.value
        return data


class ProactiveRuntime:
    def __init__(self, dedupe_seconds=5.0, desktop_cooldown_seconds=30.0,
                 max_causation_depth=MAX_CAUSATION_DEPTH, clock=None, inbox=None,
                 context_rules=None, context_rule_store=None, reasoning_policy=None,
                 action_proposer=None, lifecycle=None, attention_budget=None,
                 orchestrator=None):
        self.dedupe_seconds = float(dedupe_seconds); self.desktop_cooldown_seconds = float(desktop_cooldown_seconds); self.max_causation_depth = int(max_causation_depth); self._clock = clock or time.monotonic; self._inbox = inbox
        self._reasoning_policy = reasoning_policy or get_proactive_reasoning_policy(); self._action_proposer = action_proposer or get_proactive_action_proposer(); self._attention_budget = attention_budget or get_proactive_attention_budget(); self._orchestrator = orchestrator or get_proactive_orchestrator()
        if lifecycle is None:
            from proactive_action_lifecycle import get_proactive_action_lifecycle
            lifecycle = get_proactive_action_lifecycle()
        self._lifecycle = lifecycle
        if context_rule_store is None:
            from context_rule_store import get_context_rule_store
            context_rule_store = get_context_rule_store()
        self._context_rule_store = context_rule_store; self._context_triggers = ContextTriggerEngine(list(context_rules) if context_rules is not None else self._context_rule_store.active()); self._lock = threading.RLock(); self._recent = {}; self._last_by_type = {}; self._decisions = []; self._autonomous_sources = {}
    def _refresh_context_rules(self): self._context_triggers.set_rules(self._context_rule_store.active())
    def set_context_rules(self,rules):
        with self._lock:
            for existing in self._context_rule_store.list(): self._context_rule_store.remove(existing["id"])
            for rule in rules or []: self._context_rule_store.add(rule)
            self._refresh_context_rules()
        return self.context_rules()
    def context_rules(self): return self._context_rule_store.list()
    def add_context_rule(self,app=None,title=None,message=None,action="notify",on_transition=True,priority="normal"):
        rule=self._context_rule_store.add({"app":app,"title":title,"message":message,"action":action,"on_transition":on_transition,"priority":priority})
        with self._lock:self._refresh_context_rules()
        return rule
    def remove_context_rule(self,rule_id):
        removed=self._context_rule_store.remove(rule_id)
        if removed:
            with self._lock:self._refresh_context_rules()
        return removed
    def set_context_rule_enabled(self,rule_id,enabled):
        rule=self._context_rule_store.set_enabled(rule_id,enabled)
        if rule is not None:
            with self._lock:self._refresh_context_rules()
        return rule
    def _fingerprint(self,event): return hashlib.sha256(json.dumps({"type":event.get("type"),"payload":event.get("payload") or {}},ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")).hexdigest()
    def _depth(self,event):
        try:return int(event.get("causation_depth") or 0)
        except Exception:return 0
    def _record(self,event,decision):
        item={"event_id":event.get("id"),"event_type":event.get("type"),"timestamp":datetime.now().astimezone().isoformat(timespec="seconds"),"decision":decision.to_dict()}
        with self._lock:self._decisions.append(item);del self._decisions[:-100]
        return item
    @staticmethod
    def _message_for_failure(payload): return f"Не удалось завершить задачу «{str(payload.get('goal') or 'фоновой задачи').strip()}»: {str(payload.get('error') or 'неизвестная ошибка').strip()}"
    @staticmethod
    def _message_for_completion(payload):
        goal=str(payload.get("goal") or "задача").strip();result=str(payload.get("result") or "").strip()
        if not result:return f"Задача завершена: {goal}"
        if len(result)>MAX_COMPLETION_RESULT_CHARS:result=result[:MAX_COMPLETION_RESULT_CHARS].rstrip()+"…"
        return f"Готово: {goal}\n\n{result}"
    @staticmethod
    def _is_proactive_session(payload): return str(payload.get("session_id") or "").startswith("proactive:")
    def _release_autonomous(self,payload):
        task_id=str(payload.get("task_id") or "")
        if not task_id:return
        with self._lock:source=self._autonomous_sources.pop(task_id,None)
        if source:self._orchestrator.release(source)
    def _update_lifecycle(self,event_type,payload):
        if event_type in {"task.completed","task.failed","task.cancelled"}:self._release_autonomous(payload)
        if not self._is_proactive_session(payload):return None
        task_id=payload.get("task_id")
        if not task_id:return None
        if event_type=="task.completed":return self._lifecycle.completed(task_id,payload.get("result"))
        if event_type=="task.failed":return self._lifecycle.failed(task_id,payload.get("error"))
        if event_type=="task.cancelled":return self._lifecycle.cancelled(task_id,payload.get("error") or "Cancelled by user")
        return None
    def _context_decision(self,payload):
        matches=self._context_triggers.match(payload)
        if not matches:return None
        match=matches[0];rule=match["rule"];action=ProactiveAction.ASK_USER if rule["action"]=="ask_user" else ProactiveAction.NOTIFY
        return ProactiveDecision(action,"context_rule:"+rule["id"],notification=match["message"],source="context_trigger",priority=rule["priority"] if rule["priority"] in {"low","normal","high"} else "normal")
    def _pattern_decision(self,event_type,payload):
        autonomous=self._orchestrator.decide(event_type,payload)
        if autonomous.get("spawn"):return ProactiveDecision(ProactiveAction.SPAWN_TASK,autonomous["reason"],goal=autonomous["goal"],source="autonomous_orchestration",priority="low",source_task_id=autonomous.get("task_id"))
        recommendation=self._reasoning_policy.decide(event_type,payload)
        if recommendation is not None:
            try:action=ProactiveAction(recommendation.action)
            except ValueError:action=ProactiveAction.RECORD
            proposals=self._action_proposer.propose(event_type,payload,recommendation) if action==ProactiveAction.ASK_USER else []
            return ProactiveDecision(action,recommendation.reason,goal=recommendation.goal,notification=recommendation.notification,source="context_reasoning",priority=recommendation.priority,proposals=proposals)
        message=str(payload.get("message") or "").strip()
        if not message:return None
        if event_type=="desktop.context.dwell":return ProactiveDecision(ProactiveAction.NOTIFY,"context_dwell",notification=message,source="context_pattern",priority="low")
        if event_type=="desktop.context.repeated":return ProactiveDecision(ProactiveAction.NOTIFY,"context_repeated",notification=message,source="context_pattern",priority="normal")
        return None
    def decide(self,event,trigger_goals=None):
        trigger_goals=list(trigger_goals or []);event_type=str(event.get("type") or "");payload=event.get("payload") or {};now=self._clock()
        if self._depth(event)>=self.max_causation_depth:return ProactiveDecision(ProactiveAction.IGNORE,"max_causation_depth")
        fingerprint=self._fingerprint(event)
        with self._lock:
            last=self._recent.get(fingerprint)
            if last is not None and now-last<self.dedupe_seconds:return ProactiveDecision(ProactiveAction.IGNORE,"duplicate_event")
            self._recent[fingerprint]=now;cutoff=now-max(self.dedupe_seconds*4,60.0);self._recent={k:v for k,v in self._recent.items() if v>=cutoff};last_type=self._last_by_type.get(event_type)
            if event_type=="desktop.changed" and last_type is not None and now-last_type<self.desktop_cooldown_seconds:return ProactiveDecision(ProactiveAction.RECORD,"desktop_cooldown")
            self._last_by_type[event_type]=now
        if event_type=="schedule.due":
            goal=str(payload.get("goal") or "").strip();return ProactiveDecision(ProactiveAction.SPAWN_TASK,"explicit_schedule",goal=goal,source="scheduler",priority="high") if goal else ProactiveDecision(ProactiveAction.IGNORE,"scheduled_event_without_goal")
        if trigger_goals:return ProactiveDecision(ProactiveAction.SPAWN_TASK,"matched_trigger",goal=trigger_goals[0],source="trigger")
        if event_type=="task.failed":return ProactiveDecision(ProactiveAction.NOTIFY,"background_task_failed",notification=self._message_for_failure(payload),priority="high")
        if event_type=="task.completed":
            notify=bool(payload.get("notify"));proactive=self._is_proactive_session(payload)
            if notify or proactive:return ProactiveDecision(ProactiveAction.NOTIFY,"proactive_task_completed" if proactive and not notify else "background_task_completed",notification=self._message_for_completion(payload))
        if event_type=="proactive.question":
            question=str(payload.get("question") or "").strip();return ProactiveDecision(ProactiveAction.ASK_USER,"explicit_question",notification=question,priority="high") if question else ProactiveDecision(ProactiveAction.IGNORE,"question_without_text")
        pattern=self._pattern_decision(event_type,payload)
        if pattern is not None:return pattern
        if event_type=="desktop.changed":
            contextual=self._context_decision(payload)
            if contextual is not None:return contextual
            return ProactiveDecision(ProactiveAction.RECORD,"desktop_changed:"+",".join(map(str,payload.get("changed_fields") or ["unknown"])))
        return ProactiveDecision(ProactiveAction.RECORD,"no_actionable_policy")
    def _push_attention(self,event,decision):
        if decision.action not in {ProactiveAction.NOTIFY,ProactiveAction.ASK_USER}:return None
        if not self._attention_budget.allow(decision.action,decision.priority):return {"suppressed":True,"reason":"attention_budget"}
        inbox=self._inbox
        if inbox is None:
            from proactive_inbox import get_proactive_inbox
            inbox=get_proactive_inbox()
        return inbox.push(decision.notification,action=decision.action.value,event=event,priority=decision.priority,reason=decision.reason,proposals=decision.proposals)
    def _spawn_task(self,runtime,goal,session_id,**provenance):
        try:return runtime.spawn(goal,session_id=session_id,**provenance)
        except TypeError:return runtime.spawn(goal,session_id=session_id)
    def handle(self,event,trigger_goals=None):
        event_type=str(event.get("type") or "");payload=event.get("payload") or {};lifecycle=self._update_lifecycle(event_type,payload);decision=self.decide(event,trigger_goals);record=self._record(event,decision);result={"success":True,"event":event,"decision":decision.to_dict(),"record":record,"launched":[],"attention":None,"lifecycle":lifecycle};attention=self._push_attention(event,decision)
        if attention is not None:result["attention"]=attention
        if decision.action!=ProactiveAction.SPAWN_TASK:return result
        from task_runtime import get_runtime
        parent_event_id=event.get("id") or None;correlation_id=event.get("correlation_id") or parent_event_id
        spawn_result=self._spawn_task(get_runtime(),decision.goal,"proactive:"+str(correlation_id),parent_event_id=parent_event_id,correlation_id=correlation_id,causation_depth=self._depth(event));result["spawn"]=spawn_result
        if spawn_result.get("success"):
            spawned_task_id=spawn_result.get("task_id");result["launched"].append({"task_id":spawned_task_id,"reason":decision.reason})
            if decision.source_task_id and spawned_task_id:
                with self._lock:self._autonomous_sources[str(spawned_task_id)]=str(decision.source_task_id)
        elif decision.source_task_id:self._orchestrator.release(decision.source_task_id)
        return result
    def recent_decisions(self,limit=20):
        try:limit=int(limit)
        except Exception:limit=20
        limit=max(1,min(limit,100))
        with self._lock:return list(self._decisions[-limit:])

_runtime=None;_runtime_lock=threading.Lock()
def get_proactive_runtime():
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:_runtime=ProactiveRuntime()
    return _runtime
