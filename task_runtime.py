
"""Persistent in-process background task runtime for Akira.

A background task gets its own Session and executes independently
from the foreground conversation.
"""
from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "runtime" / "tasks"
TASK_FILE = ROOT / "runtime" / "background_tasks.json"
MAX_CONCURRENT_TASKS = 3
MAX_STORED_TASKS = 100


class TaskRuntime:
    """Threaded autonomous task manager."""

    def __init__(self, max_workers=MAX_CONCURRENT_TASKS):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="akira-bg")
        self._lock = threading.RLock(); self._tasks = {}; self._futures = {}; self._load()

    def _load(self):
        TASK_DIR.mkdir(parents=True, exist_ok=True)
        if not TASK_FILE.exists(): return
        try: payload = json.loads(TASK_FILE.read_text(encoding="utf-8"))
        except Exception: return
        if not isinstance(payload, list): return
        for task in payload[-MAX_STORED_TASKS:]:
            if not isinstance(task, dict) or not task.get("id"): continue
            if task.get("status") == "running": task["status"] = "interrupted"; task["error"] = "Akira process was restarted before this background task completed."; task["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self._tasks[task["id"]] = task
        self._save()
    def _save(self):
        TASK_DIR.mkdir(parents=True, exist_ok=True); data=list(self._tasks.values())[-MAX_STORED_TASKS:]; temporary=TASK_FILE.with_suffix(".json.tmp"); temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); temporary.replace(TASK_FILE)
    def _active_count(self): return sum(1 for task in self._tasks.values() if task.get("status") in {"queued","running"})
    def _make_task(self,goal,session_id=None,*,parent_event_id=None,correlation_id=None,causation_depth=0):
        task_id=uuid.uuid4().hex[:12];now=datetime.now().isoformat(timespec="seconds");session_id=session_id or f"background:{task_id}"
        if correlation_id is None and str(session_id).startswith("proactive:"):correlation_id=str(session_id).split(":",1)[1] or None
        try:causation_depth=max(0,int(causation_depth or 0))
        except Exception:causation_depth=0
        return {"id":task_id,"goal":str(goal).strip(),"session_id":session_id,"parent_event_id":parent_event_id,"correlation_id":correlation_id,"causation_depth":causation_depth,"status":"queued","created_at":now,"started_at":None,"finished_at":None,"result":None,"error":None}
    def spawn(self,goal,session_id=None,*,parent_event_id=None,correlation_id=None,causation_depth=0):
        goal=str(goal or "").strip()
        if not goal:return {"success":False,"error":"empty_goal","output":"Нельзя создать background task с пустой целью."}
        with self._lock:
            if self._active_count()>=self.max_workers:return {"success":False,"error":"background_capacity","output":f"Достигнут лимит одновременно работающих background tasks: {self.max_workers}."}
            task=self._make_task(goal,session_id,parent_event_id=parent_event_id,correlation_id=correlation_id,causation_depth=causation_depth);task_id=task["id"];self._tasks[task_id]=task
            task["status"]="running";task["started_at"]=datetime.now().isoformat(timespec="seconds");self._save()
            try:
                future=self._executor.submit(self._run,task_id);self._futures[task_id]=future
            except Exception as error:
                task["status"]="failed";task["error"]=str(error);task["result"]=None;task["finished_at"]=datetime.now().isoformat(timespec="seconds");self._save()
                return {"success":False,"error":"task_submit_failed","task_id":task_id,"status":"failed","output":f"Не удалось запустить background task: {error}"}
        return {"success":True,"task_id":task_id,"status":"running","goal":goal,"output":f"Background task {task_id} запущен."}
    def cancel(self,task_id,reason="Cancelled by user"):
        task_id=str(task_id); cancelled_task=None
        with self._lock:
            task=self._tasks.get(task_id)
            if task is None:return {"success":False,"error":"task_not_found","task_id":task_id}
            if task.get("status") in {"completed","failed","cancelled","interrupted"}:return {"success":False,"error":"task_not_active","task_id":task_id,"status":task.get("status")}
            future=self._futures.get(task_id)
            if future is None or not future.cancel():return {"success":False,"error":"task_already_running","task_id":task_id,"status":task.get("status")}
            task["status"]="cancelled";task["error"]=str(reason);task["finished_at"]=datetime.now().isoformat(timespec="seconds");self._futures.pop(task_id,None);self._save();cancelled_task=dict(task)
        self._emit("task.cancelled",{"task_id":task_id,"goal":cancelled_task.get("goal"),"error":cancelled_task.get("error"),"session_id":cancelled_task.get("session_id")},task=cancelled_task)
        return {"success":True,"task_id":task_id,"status":"cancelled"}
    def _run(self,task_id):
        try:
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None or task.get("status")=="cancelled":return
                goal=task["goal"];session_id=task["session_id"]
            from brain import ask
            result=ask(goal,session_id=session_id)
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None or task.get("status")=="cancelled":return
                task["status"]="completed";task["result"]=str(result);task["finished_at"]=datetime.now().isoformat(timespec="seconds");task["error"]=None;self._save();self._emit("task.completed",{"task_id":task_id,"goal":goal,"result":str(result),"session_id":session_id},task=task)
        except Exception as error:
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None or task.get("status")=="cancelled":return
                task["status"]="failed";task["error"]=str(error);task["result"]=None;task["finished_at"]=datetime.now().isoformat(timespec="seconds");task["traceback"]=traceback.format_exc()[-4000:];self._save();self._emit("task.failed",{"task_id":task_id,"goal":task.get("goal"),"error":str(error),"session_id":task.get("session_id")},task=task)
        finally:
            with self._lock:self._futures.pop(task_id,None);self._save()
    @staticmethod
    def _emit(event_type,payload,task=None):
        try:
            from event_bus import emit_event
            metadata={"source":"task_runtime"};task=task or {};correlation_id=task.get("correlation_id");parent_event_id=task.get("parent_event_id") or correlation_id
            if correlation_id:metadata["correlation_id"]=correlation_id
            if parent_event_id:
                metadata["parent_event_id"]=parent_event_id
                try:metadata["causation_depth"]=max(0,int(task.get("causation_depth") or 0))+1
                except Exception:metadata["causation_depth"]=1
            emit_event(event_type,payload,**metadata)
        except Exception as event_error:print("[Akira task runtime] event error:",event_error)
    def status(self,task_id):
        with self._lock:
            task=self._tasks.get(str(task_id))
            if task is None:return {"success":False,"error":"task_not_found","output":f"Task {task_id} не найден."}
            return {"success":True,"task":dict(task),"output":json.dumps(task,ensure_ascii=False,indent=2)}
    def list_tasks(self,limit=20):
        try:limit=int(limit)
        except Exception:limit=20
        limit=max(1,min(limit,50))
        with self._lock:
            tasks=list(self._tasks.values())[-limit:];tasks.reverse();return {"success":True,"tasks":tasks,"output":json.dumps(tasks,ensure_ascii=False,indent=2)}
    def result(self,task_id):
        response=self.status(task_id)
        if not response.get("success"):return response
        task=response["task"];status=task.get("status")
        if status=="completed":return {"success":True,"ready":True,"task_id":task_id,"result":task.get("result"),"output":str(task.get("result") or "")}
        if status in {"failed","cancelled","interrupted"}:return {"success":False,"ready":True,"task_id":task_id,"error":task.get("error"),"status":status,"output":f"Background task {status}: {task.get('error') or ''}"}
        return {"success":True,"ready":False,"task_id":task_id,"status":status,"output":f"Task {task_id} ещё выполняется."}

_runtime=None;_runtime_lock=threading.Lock()
def get_runtime():
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:_runtime=TaskRuntime()
    return _runtime
def background_task_start(goal):return get_runtime().spawn(goal)
def background_task_status(task_id):return get_runtime().status(task_id)
def background_tasks(limit=20):return get_runtime().list_tasks(limit)
def background_task_result(task_id):return get_runtime().result(task_id)
def background_task_cancel(task_id):return get_runtime().cancel(task_id)