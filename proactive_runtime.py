"""Event-driven proactive runtime for Akira."""
from __future__ import annotations
import hashlib,json,threading,time
from dataclasses import dataclass,asdict
from datetime import datetime
from enum import Enum
MAX_CAUSATION_DEPTH=3
class ProactiveAction(str,Enum):
 IGNORE="ignore"; RECORD="record"; NOTIFY="notify"; SPAWN_TASK="spawn_task"; ASK_USER="ask_user"
@dataclass
class ProactiveDecision:
 action:ProactiveAction; reason:str; goal:str|None=None; notification:str|None=None; source:str="policy"
 def to_dict(self):
  data=asdict(self);data["action"]=self.action.value;return data
class ProactiveRuntime:
 def __init__(self,dedupe_seconds=5.0,desktop_cooldown_seconds=30.0,max_causation_depth=MAX_CAUSATION_DEPTH,clock=None):
  self.dedupe_seconds=float(dedupe_seconds);self.desktop_cooldown_seconds=float(desktop_cooldown_seconds);self.max_causation_depth=int(max_causation_depth);self._clock=clock or time.monotonic;self._lock=threading.RLock();self._recent={};self._last_by_type={};self._decisions=[]
 def _fingerprint(self,event):
  return hashlib.sha256(json.dumps({"type":event.get("type"),"payload":event.get("payload") or {}},ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")).hexdigest()
 def _depth(self,event):
  try:return int(event.get("causation_depth") or 0)
  except Exception:return 0
 def _record(self,event,decision):
  item={"event_id":event.get("id"),"event_type":event.get("type"),"timestamp":datetime.now().astimezone().isoformat(timespec="seconds"),"decision":decision.to_dict()}
  with self._lock:self._decisions.append(item);del self._decisions[:-100]
  return item
 def decide(self,event,trigger_goals=None):
  trigger_goals=list(trigger_goals or []);event_type=str(event.get("type") or "");now=self._clock()
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
   goal=str((event.get("payload") or {}).get("goal") or "").strip()
   if not goal:return ProactiveDecision(ProactiveAction.IGNORE,"scheduled_event_without_goal")
   return ProactiveDecision(ProactiveAction.SPAWN_TASK,"explicit_schedule",goal=goal,source="scheduler")
  if trigger_goals:return ProactiveDecision(ProactiveAction.SPAWN_TASK,"matched_trigger",goal=trigger_goals[0],source="trigger")
  if event_type=="task.failed":return ProactiveDecision(ProactiveAction.NOTIFY,"background_task_failed",notification="Фоновая задача Акиры завершилась ошибкой.")
  return ProactiveDecision(ProactiveAction.RECORD,"no_actionable_policy")
 def handle(self,event,trigger_goals=None):
  decision=self.decide(event,trigger_goals);record=self._record(event,decision);result={"success":True,"event":event,"decision":decision.to_dict(),"record":record,"launched":[]}
  if decision.action!=ProactiveAction.SPAWN_TASK:return result
  from task_runtime import get_runtime
  correlation_id=event.get("correlation_id") or event.get("id")
  spawn_result=get_runtime().spawn(decision.goal,session_id="proactive:"+str(correlation_id))
  result["spawn"]=spawn_result
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
