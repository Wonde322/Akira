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

    def to_dict(self):
        data = asdict(self)
        data["action"] = self.action.value
        return data


class ProactiveRuntime:
    def __init__(self, dedupe_seconds=5.0, desktop_cooldown_seconds=30.0,
                 max_causation_depth=MAX_CAUSATION_DEPTH, clock=None, inbox=None,
                 context_rules=None, context_rule_store=None, reasoning_policy=None,
                 action_proposer=None, lifecycle=None):
        self.dedupe_seconds = float(dedupe_seconds)
        self.desktop_cooldown_seconds = float(desktop_cooldown_seconds)
        self.max_causation_depth = int(max_causation_depth)
        self._clock = clock or time.monotonic
        self._inbox = inbox
        self._reasoning_policy = reasoning_policy or get_proactive_reasoning_policy()
        self._action_proposer = action_proposer or get_proactive_action_proposer()
        if lifecycle is None:
            from proactive_action_lifecycle import get_proactive_action_lifecycle
            lifecycle = get_proactive_action_lifecycle()
        self._lifecycle = lifecycle
        if context_rule_store is None:
            from context_rule_store import get_context_rule_store
            context_rule_store = get_context_rule_store()
        self._context_rule_store = context_rule_store
        initial_rules = list(context_rules) if context_rules is not None else self._context_rule_store.active()
        self._context_triggers = ContextTriggerEngine(initial_rules)
        self._lock = threading.RLock()
        self._recent = {}
        self._last_by_type = {}
        self._decisions = []

    def _refresh_context_rules(self): self._context_triggers.set_rules(self._context_rule_store.active())
    def set_context_rules(self, rules):
        with self._lock:
            for existing in self._context_rule_store.list(): self._context_rule_store.remove(existing["id"])
            for rule in rules or []: self._context_rule_store.add(rule)
            self._refresh_context_rules()
        return self.context_rules()
    def context_rules(self): return self._context_rule_store.list()
    def add_context_rule(self, app=None, title=None, message=None, action="notify", on_transition=True, priority="normal"):
        rule=self._context_rule_store.add({"app":app,"title":title,"message":message,"action":action,"on_transition":on_transition,"priority":priority})
        with self._lock:self._refresh_context_rules()
        return rule
    def remove_context_rule(self, rule_id):
        removed=self._context_rule_store.remove(rule_id)
        if removed:
            with self._lock:self._refresh_context_rules()
        return removed
    def set_context_rule_enabled(self, rule_id, enabled):
        rule=self._context_rule_store.set_enabled(rule_id, enabled)
        if rule is not None:
            with self._lock:self._refresh_context_rules()
        return rule
    def _fingerprint(self,event):
        encoded=json.dumps({"type":event.get("type"),"payload":event.get("payload") or {}},ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
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
    def _update_lifecycle(self,event_type,payload):
        if not self._is_proactive_session(payload): return None
        task_id=payload.get("task_id")
        if not task_id:return None
        if event_type=="task.completed": return self._lifecycle.completed(task_id,payload.get("result"))
        if event_type=="task.failed": return self._lifecycle.failed(task_id,payload.get("error"))
        return None
    def _context_decision(self,payload):
        matches=self._context_triggers.match(payload)
        if not matches:return None
        match=matches[0];rule=match["rule"];action=ProactiveAction.ASK_USER if rule["action"]=="ask_user" else ProactiveAction.NOTIFY
        return ProactiveDecision(action,"context_rule:"+rule["id"],notification=match["message"],source="context_trigger",priority=rule["priority"] if rule["priority"] in {"low","normal","high"} else "normal")
    def _pattern_decision(self,event_type,payload):
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
            self._recent[fingerprint]=now;cutoff=now-max(self.dedupe_seconds*4,60.0);self._recent={k:v for k,v in self._recent.items() if v>=cutoff}
            last_type=self._last_by_type.get(event_type)
            if event_type=="desktop.changed" and last_type is not None and now-last_type<self.desktop_cooldown_seconds:return ProactiveDecision(ProactiveAction.RECORD,"desktop_cooldown")
            self._last_by_type[event_type]=now
        if event_type=="schedule.due":
            goal=str(payload.get("goal") or "").strip();return ProactiveDecision(ProactiveAction.SPAWN_TASK,"explicit_schedule",goal=goal,source="scheduler",priority="high") if goal else ProactiveDecision(ProactiveAction.IGNORE,"scheduled_event_without_goal")
        if trigger_goals:return ProactiveDecision(ProactiveAction.SPAWN_TASK,"matched_trigger",goal=trigger_goals[0],source="trigger")
        if event_type=="task.failed":return ProactiveDecision(ProactiveAction.NOTIFY,"background_task_failed",notification=self._message_for_failure(payload),priority="high")
        if event_type=="task.completed":
            notify=bool(payload.get("notify"));proactive=self._is_proactive_session(payload)
            if notify or proactive:
                goal=str(payload.get("goal") or "задача");reason="proactive_task_completed" if proactive and not notify else "background_task_completed"
                return ProactiveDecision(ProactiveAction.NOTIFY,reason,notification=self._message_for_completion(payload))
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
        inbox=self._inbox
        if inbox is None:
            from proactive_inbox import get_proactive_inbox
            inbox=get_proactive_inbox()
        return inbox.push(decision.notification,action=decision.action.value,event=event,priority=decision.priority,reason=decision.reason,proposals=decision.proposals)
    def handle(self,event,trigger_goals=None):
        event_type=str(event.get("type") or "");payload=event.get("payload") or {};lifecycle=self._update_lifecycle(event_type,payload)
        decision=self.decide(event,trigger_goals);record=self._record(event,decision)
        result={"success":True,"event":event,"decision":decision.to_dict(),"record":record,"launched":[],"attention":None,"lifecycle":lifecycle}
        attention=self._push_attention(event,decision)
        if attention is not None:result["attention"]=attention
        if decision.action!=ProactiveAction.SPAWN_TASK:return result
        from task_runtime import get_runtime
        correlation_id=event.get("correlation_id") or event.get("id");spawn_result=get_runtime().spawn(decision.goal,session_id="proactive:"+str(correlation_id));result["spawn"]=spawn_result
        if spawn_result.get("success"):result["launched"].append({"task_id":spawn_result.get("task_id"),"reason":decision.reason})
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
