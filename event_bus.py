"""Persistent event bus for Akira.

The bus transports and persists events. Decisions about autonomous work belong to proactive_runtime.
"""
from __future__ import annotations
import json, threading, uuid
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUNTIME_DIR=ROOT/"runtime"
EVENT_LOG=RUNTIME_DIR/"events.jsonl"
TRIGGER_FILE=RUNTIME_DIR/"triggers.json"
MAX_TRIGGERS=200
MAX_EVENT_LOG_BYTES=2_000_000
MAX_TRIGGER_CORRELATIONS=32
def _now(): return datetime.now().astimezone()
def _iso(value=None): return (value or _now()).isoformat(timespec="seconds")
class EventBus:
 def __init__(self): self._lock=threading.RLock(); self._triggers={}; RUNTIME_DIR.mkdir(parents=True,exist_ok=True); self._load_triggers()
 def _load_triggers(self):
  if not TRIGGER_FILE.exists(): return
  try:data=json.loads(TRIGGER_FILE.read_text(encoding="utf-8"))
  except Exception:return
  if isinstance(data,list):
   for trigger in data[-MAX_TRIGGERS:]:
    if isinstance(trigger,dict) and trigger.get("id"):
     correlations=trigger.get("recent_correlations")
     trigger["recent_correlations"]=[str(value) for value in correlations[-MAX_TRIGGER_CORRELATIONS:]] if isinstance(correlations,list) else []
     self._triggers[trigger["id"]]=trigger
 def _save_triggers(self):
  tmp=TRIGGER_FILE.with_suffix(".json.tmp");tmp.write_text(json.dumps(list(self._triggers.values())[-MAX_TRIGGERS:],ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(TRIGGER_FILE)
 def _append_event(self,event):
  RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
  if EVENT_LOG.exists():
   try:
    if EVENT_LOG.stat().st_size>MAX_EVENT_LOG_BYTES:EVENT_LOG.write_text("\n".join(EVENT_LOG.read_text(encoding="utf-8").splitlines()[-1000:])+"\n",encoding="utf-8")
   except Exception:pass
  with EVENT_LOG.open("a",encoding="utf-8") as f:f.write(json.dumps(event,ensure_ascii=False,default=str)+"\n")
 def create_trigger(self,event_type,goal,cooldown_seconds=0):
  event_type=str(event_type or "").strip();goal=str(goal or "").strip()
  if not event_type:return {"success":False,"error":"empty_event_type","output":"Не указан event_type."}
  if not goal:return {"success":False,"error":"empty_goal","output":"Не указана trigger goal."}
  try:cooldown=max(0,int(cooldown_seconds or 0))
  except Exception:return {"success":False,"error":"invalid_cooldown","output":"cooldown_seconds должен быть числом."}
  tid=uuid.uuid4().hex[:12];trigger={"id":tid,"event_type":event_type,"goal":goal,"enabled":True,"cooldown_seconds":cooldown,"created_at":_iso(),"last_fired_at":None,"fire_count":0,"last_task_id":None,"last_error":None,"recent_correlations":[]}
  with self._lock:self._triggers[tid]=trigger;self._save_triggers()
  return {"success":True,"trigger_id":tid,"trigger":dict(trigger),"output":f"Trigger {tid} создан."}
 def cancel_trigger(self,trigger_id):
  with self._lock:
   trigger=self._triggers.get(str(trigger_id or ""))
   if trigger is None:return {"success":False,"error":"trigger_not_found","output":f"Trigger {trigger_id} не найден."}
   trigger["enabled"]=False;trigger["cancelled_at"]=_iso();self._save_triggers()
  return {"success":True,"trigger_id":str(trigger_id),"output":f"Trigger {trigger_id} отключён."}
 def list_triggers(self,limit=100):
  try:limit=int(limit)
  except Exception:limit=100
  limit=max(1,min(limit,100))
  with self._lock:data=list(self._triggers.values())[-limit:];data.reverse()
  return {"success":True,"triggers":data,"output":json.dumps(data,ensure_ascii=False,indent=2)}
 def _correlation_seen(self,trigger,correlation_id):return bool(correlation_id) and str(correlation_id) in set(str(value) for value in trigger.get("recent_correlations") or [])
 def _remember_correlation(self,trigger,correlation_id):
  if not correlation_id:return
  correlations=[str(value) for value in trigger.get("recent_correlations") or [] if str(value)!=str(correlation_id)];correlations.append(str(correlation_id));trigger["recent_correlations"]=correlations[-MAX_TRIGGER_CORRELATIONS:]
 def _forget_correlation(self,trigger,correlation_id):
  if not correlation_id:return
  trigger["recent_correlations"]=[str(value) for value in trigger.get("recent_correlations") or [] if str(value)!=str(correlation_id)]
 def _trigger_still_enabled(self,trigger_id,correlation_id):
  with self._lock:
   current=self._triggers.get(trigger_id)
   if current is not None and current.get("enabled"):return True
   if current is not None:self._forget_correlation(current,correlation_id);self._save_triggers()
  return False
 def _record_results(self,results,correlation_id):
  with self._lock:
   for trigger,result in results:
    current=self._triggers.get(trigger["id"])
    if current is None:continue
    if isinstance(result,Exception):
     current["last_error"]=str(result);self._forget_correlation(current,correlation_id);continue
    spawn=result.get("spawn") or {}
    if spawn.get("success"):
     current["last_fired_at"]=_iso();current["fire_count"]=int(current.get("fire_count") or 0)+1;current["last_task_id"]=spawn.get("task_id");current["last_error"]=None
    elif result.get("decision",{}).get("action")=="spawn_task":
     current["last_error"]=spawn.get("error") or spawn.get("output");self._forget_correlation(current,correlation_id)
    else:self._forget_correlation(current,correlation_id)
   self._save_triggers()
 def emit(self,event_type,payload=None,*,parent_event_id=None,correlation_id=None,causation_depth=0,source="system"):
  eid=uuid.uuid4().hex[:16];event={"id":eid,"type":str(event_type),"timestamp":_iso(),"payload":payload if isinstance(payload,dict) else {},"parent_event_id":parent_event_id,"correlation_id":correlation_id or parent_event_id or eid,"causation_depth":max(0,int(causation_depth or 0)),"source":str(source or "system")}
  with self._lock:
   self._append_event(event);matched=[dict(t) for t in self._triggers.values() if t.get("enabled") and t.get("event_type")==event["type"]]
   eligible=[t for t in matched if not self._cooldown_active(t) and not self._correlation_seen(t,event.get("correlation_id"))]
   for trigger in eligible:
    current=self._triggers.get(trigger["id"])
    if current is not None:self._remember_correlation(current,event.get("correlation_id"))
   if eligible:self._save_triggers()
  try:
   from proactive_runtime import get_proactive_runtime
   runtime=get_proactive_runtime()
  except Exception as error:
   with self._lock:
    for trigger in eligible:
     current=self._triggers.get(trigger["id"])
     if current is not None:self._forget_correlation(current,event.get("correlation_id"))
    if eligible:self._save_triggers()
   return {"success":False,"event":event,"error":"proactive_runtime_error","output":str(error)}
  results=[]
  if eligible:
   for trigger in eligible:
    if not self._trigger_still_enabled(trigger["id"],event.get("correlation_id")):continue
    dispatched=dict(event);dispatched["trigger_id"]=trigger["id"]
    try:result=runtime.handle(dispatched,[self._render_goal(trigger.get("goal",""),event)])
    except Exception as error:result=error
    results.append((trigger,result))
   self._record_results(results,event.get("correlation_id"))
  else:
   try:results=[(None,runtime.handle(event,[]))]
   except Exception as error:return {"success":False,"event":event,"error":"proactive_runtime_error","output":str(error)}
  launched=[item for _,result in results if not isinstance(result,Exception) for item in result.get("launched",[])]
  decisions=[result.get("decision") for _,result in results if not isinstance(result,Exception)]
  errors=[str(result) for _,result in results if isinstance(result,Exception)]
  return {"success":not errors,"event":event,"launched":launched,"decision":decisions[0] if len(decisions)==1 else decisions,"error":"proactive_runtime_error" if errors else None,"output":str(errors[0]) if errors and not launched else json.dumps(launched,ensure_ascii=False)}
 def _cooldown_active(self,trigger):
  cooldown=int(trigger.get("cooldown_seconds") or 0);last=trigger.get("last_fired_at")
  if cooldown<=0 or not last:return False
  try:timestamp=datetime.fromisoformat(last)
  except Exception:return False
  return (_now()-timestamp).total_seconds()<cooldown
 def _render_goal(self,goal,event):
  payload=event.get("payload",{});result=str(goal)
  for key,value in {"{{event.type}}":str(event.get("type","")),"{{event.id}}":str(event.get("id","")),"{{event.timestamp}}":str(event.get("timestamp","")),"{{event.payload}}":json.dumps(payload,ensure_ascii=False)}.items():result=result.replace(key,value)
  return result
_bus=None;_bus_lock=threading.Lock()
def get_event_bus():
 global _bus
 if _bus is None:
  with _bus_lock:
   if _bus is None:_bus=EventBus()
 return _bus
def create_trigger(event_type,goal,cooldown_seconds=0):return get_event_bus().create_trigger(event_type,goal,cooldown_seconds)
def cancel_trigger(trigger_id):return get_event_bus().cancel_trigger(trigger_id)
def list_triggers(limit=100):return get_event_bus().list_triggers(limit)
def emit_event(event_type,payload=None,**metadata):return get_event_bus().emit(event_type,payload,**metadata)
