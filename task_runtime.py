"""Persistent autonomous task runtime."""
from __future__ import annotations
import json, os, tempfile, threading, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent; TASK_DIR=ROOT/"runtime"/"tasks"; TASK_FILE=ROOT/"runtime"/"background_tasks.json"; MAX_CONCURRENT_TASKS=3; MAX_STORED_TASKS=100
TERMINAL={"completed","failed","cancelled","interrupted"}; ACTIVE={"queued","running","cancelling"}
def _now(): return datetime.now().astimezone().isoformat(timespec="seconds")
class TaskRuntime:
 def __init__(self,max_workers=MAX_CONCURRENT_TASKS):
  if isinstance(max_workers,bool) or int(max_workers)<1: raise ValueError("max_workers must be a positive integer")
  self.max_workers=int(max_workers); self._executor=ThreadPoolExecutor(max_workers=self.max_workers); self._lock=threading.RLock(); self._tasks={}; self._futures={}; self._load()
 def _load(self):
  if not TASK_FILE.exists(): return
  try: rows=json.loads(TASK_FILE.read_text(encoding="utf-8"))
  except (OSError,UnicodeDecodeError,json.JSONDecodeError): return
  if not isinstance(rows,list): return
  dirty=False
  for r in rows[-MAX_STORED_TASKS:]:
   if not isinstance(r,dict) or not r.get("id") or not str(r.get("goal") or "").strip(): continue
   t=dict(r); t["id"]=str(t["id"]); t["goal"]=str(t["goal"]).strip(); t.setdefault("session_id",f"background:{t['id']}"); t.setdefault("result",None); t.setdefault("error",None)
   if t.get("status") in ACTIVE: t.update(status="interrupted",error="Akira process was restarted before this background task completed.",finished_at=_now()); dirty=True
   self._tasks[t["id"]]=t
  if dirty:self._save()
 def _save(self):
  TASK_FILE.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(dir=TASK_FILE.parent,prefix=".tasks-",suffix=".tmp")
  try:
   with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(list(self._tasks.values())[-MAX_STORED_TASKS:],f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
   os.replace(tmp,TASK_FILE)
  except Exception:
   try: os.unlink(tmp)
   except FileNotFoundError: pass
   raise
 def _make_task(self,goal,session_id=None,**kw):
  i=uuid.uuid4().hex[:12]; return {"id":i,"goal":str(goal).strip(),"session_id":str(session_id or f"background:{i}"),"status":"queued","created_at":_now(),"started_at":None,"finished_at":None,"result":None,"error":None,**kw}
 def spawn(self,goal,session_id=None,**kw):
  goal=str(goal or "").strip()
  if not goal:return {"success":False,"error":"empty_goal"}
  with self._lock:
   if sum(t.get("status") in ACTIVE for t in self._tasks.values())>=self.max_workers:return {"success":False,"error":"background_capacity"}
   t=self._make_task(goal,session_id,**kw); i=t["id"]; self._tasks[i]=t
   try:
    f=self._executor.submit(self._run,i)
    if t["status"] not in TERMINAL:t.update(status="running",started_at=_now())
    if not (callable(getattr(f,"done",None)) and f.done()) and t["status"] not in TERMINAL:self._futures[i]=f
    self._save()
   except Exception as e:t.update(status="failed",error=str(e),finished_at=_now()); self._save(); return {"success":False,"error":"task_submit_failed","task_id":i,"status":"failed"}
   return {"success":True,"task_id":i,"status":t["status"],"goal":goal,"output":f"Background task {i} запущен."}
 def _run(self,i):
  try:
   with self._lock:
    t=self._tasks.get(i)
    if not t:return
    if t["status"] in {"cancelled","cancelling"}:t.update(status="cancelled",finished_at=_now()); self._save(); return
    goal,sid=t["goal"],t["session_id"]
   from agent_runtime import get_agent_runtime
   r=get_agent_runtime().run(goal,session_id=sid,mode="background",task_id=i)
   with self._lock:
    t=self._tasks.get(i)
    if t and t["status"] not in TERMINAL:t.update(status="completed",result=str(r),error=None,finished_at=_now()); self._save()
  except Exception as e:
   with self._lock:
    t=self._tasks.get(i)
    if t and t["status"] not in TERMINAL:t.update(status="failed",error=str(e),finished_at=_now(),traceback=traceback.format_exc()[-4000:]); self._save()
  finally:
   with self._lock:self._futures.pop(i,None)
 def status(self,i):
  with self._lock:
   t=self._tasks.get(str(i)); return {"success":False,"error":"task_not_found"} if t is None else {"success":True,"task":dict(t),"output":json.dumps(t,ensure_ascii=False)}
 def list_tasks(self,limit=20):
  with self._lock:
   try:limit=max(1,min(int(limit),50))
   except (TypeError,ValueError):limit=20
   ts=[dict(x) for x in list(self._tasks.values())[-limit:]][::-1]; return {"success":True,"tasks":ts,"output":json.dumps(ts,ensure_ascii=False)}
 def result(self,i):
  r=self.status(i)
  if not r.get("success"):return r
  t=r["task"]
  if t["status"]=="completed":return {"success":True,"ready":True,"task_id":i,"result":t.get("result"),"output":str(t.get("result") or "")}
  return {"success":t["status"] not in TERMINAL,"ready":t["status"] in TERMINAL,"task_id":i,"status":t["status"],"error":t.get("error")}
 def cancel(self,i,reason="Cancelled by user"):
  with self._lock:
   t=self._tasks.get(str(i))
   if not t:return {"success":False,"error":"task_not_found","task_id":str(i)}
   if t["status"] in TERMINAL:return {"success":False,"error":"task_not_active","status":t["status"]}
   f=self._futures.get(str(i)); t.update(status="cancelled" if f is not None and f.cancel() else "cancelling",error=str(reason),finished_at=_now() if f is not None and f.cancelled() else None); self._futures.pop(str(i),None) if t["status"]=="cancelled" else None; self._save(); return {"success":True,"task_id":str(i),"status":t["status"]}
 def shutdown(self,wait=True):self._executor.shutdown(wait=bool(wait),cancel_futures=True)
_runtime=None; _lock=threading.Lock()
def get_runtime():
 global _runtime
 if _runtime is None:
  with _lock:
   if _runtime is None:_runtime=TaskRuntime()
 return _runtime
def spawn_task(goal,session_id=None,**kw):return get_runtime().spawn(goal,session_id,**kw)
def task_status(i):return get_runtime().status(i)
def task_result(i):return get_runtime().result(i)
def cancel_task(i,reason="Cancelled by user"):return get_runtime().cancel(i,reason)
def list_tasks(limit=20):return get_runtime().list_tasks(limit)
def background_task_start(goal,session_id=None,**kw):return spawn_task(goal,session_id,**kw)
def background_task_status(i):return task_status(i)
def background_task_result(i):return task_result(i)
def background_task_cancel(i,reason="Cancelled by user"):return cancel_task(i,reason)
def background_tasks(limit=20):return list_tasks(limit)
