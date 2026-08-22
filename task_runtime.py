"""Persistent autonomous task runtime for Akira."""
from __future__ import annotations
import json, threading, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASK_DIR=ROOT/"runtime"/"tasks"; TASK_FILE=ROOT/"runtime"/"background_tasks.json"
MAX_CONCURRENT_TASKS=3; MAX_STORED_TASKS=100
_TERMINAL_STATUSES={"completed","failed","cancelled","interrupted"}
_VALID_STATUSES=_TERMINAL_STATUSES|{"queued","running","cancelling"}

class TaskRuntime:
    """Persistent threaded scheduler for autonomous agent work."""
    def __init__(self,max_workers=MAX_CONCURRENT_TASKS):
        self.max_workers=max_workers; self._executor=ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix="akira-bg")
        self._lock=threading.RLock(); self._tasks={}; self._futures={}; self._load()
    @staticmethod
    def _normalize_loaded_task(raw):
        if not isinstance(raw,dict): return None
        task_id=str(raw.get("id") or "").strip(); goal=str(raw.get("goal") or "").strip()
        if not task_id or not goal:return None
        status=str(raw.get("status") or "failed").strip().lower()
        if status not in _VALID_STATUSES:status="failed"
        if status in {"queued","running","cancelling"}:status="interrupted"
        session_id=str(raw.get("session_id") or f"background:{task_id}").strip() or f"background:{task_id}"
        normalized=dict(raw); normalized.update({"id":task_id,"goal":goal,"session_id":session_id,"status":status})
        try: normalized["causation_depth"]=max(0,int(raw.get("causation_depth") or 0))
        except Exception: normalized["causation_depth"]=0
        for key in ("parent_event_id","correlation_id"):
            value=raw.get(key); normalized[key]=str(value).strip() if value is not None and str(value).strip() else None
        for key in ("created_at","started_at","finished_at"):
            value=raw.get(key); normalized[key]=str(value) if value is not None else None
        normalized.setdefault("result",None); normalized.setdefault("error",None); return normalized
    def _load(self):
        TASK_DIR.mkdir(parents=True,exist_ok=True)
        if not TASK_FILE.exists():return
        try: payload=json.loads(TASK_FILE.read_text(encoding="utf-8"))
        except Exception:return
        if not isinstance(payload,list):return
        interrupted=[]
        for raw in payload[-MAX_STORED_TASKS:]:
            task=self._normalize_loaded_task(raw)
            if task is None:continue
            if task.get("status")=="interrupted":
                task["error"]="Akira process was restarted before this background task completed."; task["finished_at"]=datetime.now().isoformat(timespec="seconds"); interrupted.append(dict(task))
            self._tasks[task["id"]]=task
        self._save()
        for task in interrupted:self._emit("task.interrupted",self._event_payload(task,error=task.get("error")),task=task)
    def _save(self):
        TASK_DIR.mkdir(parents=True,exist_ok=True); temporary=TASK_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(list(self._tasks.values())[-MAX_STORED_TASKS:],ensure_ascii=False,indent=2),encoding="utf-8"); temporary.replace(TASK_FILE)
    def _active_count(self):return sum(1 for t in self._tasks.values() if t.get("status") in {"queued","running","cancelling"})
    def _make_task(self,goal,session_id=None,*,parent_event_id=None,correlation_id=None,causation_depth=0):
        task_id=uuid.uuid4().hex[:12]; now=datetime.now().isoformat(timespec="seconds"); session_id=session_id or f"background:{task_id}"
        if correlation_id is None and str(session_id).startswith("proactive:"):correlation_id=str(session_id).split(":",1)[1] or None
        try:causation_depth=max(0,int(causation_depth or 0))
        except Exception:causation_depth=0
        return {"id":task_id,"goal":str(goal).strip(),"session_id":session_id,"parent_event_id":parent_event_id,"correlation_id":correlation_id,"causation_depth":causation_depth,"status":"queued","created_at":now,"started_at":None,"finished_at":None,"result":None,"error":None}
    @staticmethod
    def _event_payload(task,*,result=None,error=None):
        payload={"task_id":task.get("id"),"goal":task.get("goal")}
        if result is not None:payload["result"]=result
        if error is not None:payload["error"]=error
        payload["session_id"]=task.get("session_id"); return payload
    def spawn(self,goal,session_id=None,*,parent_event_id=None,correlation_id=None,causation_depth=0):
        goal=str(goal or "").strip()
        if not goal:return {"success":False,"error":"empty_goal","output":"Нельзя создать background task с пустой целью."}
        failed_task=None
        with self._lock:
            if self._active_count()>=self.max_workers:return {"success":False,"error":"background_capacity","output":f"Достигнут лимит одновременно работающих background tasks: {self.max_workers}."}
            task=self._make_task(goal,session_id,parent_event_id=parent_event_id,correlation_id=correlation_id,causation_depth=causation_depth); task_id=task["id"]; self._tasks[task_id]=task
            try:
                future=self._executor.submit(self._run,task_id)
                if task.get("status") not in _TERMINAL_STATUSES:
                    task["status"]="running"; task["started_at"]=datetime.now().isoformat(timespec="seconds")
                    if not future.done():self._futures[task_id]=future
                self._save()
            except Exception as error:
                task["status"]="failed"; task["error"]=str(error); task["result"]=None; task["finished_at"]=datetime.now().isoformat(timespec="seconds"); task["started_at"]=None; self._save(); failed_task=dict(task)
        if failed_task is not None:
            self._emit("task.failed",self._event_payload(failed_task,error=failed_task.get("error")),task=failed_task)
            return {"success":False,"error":"task_submit_failed","task_id":task_id,"status":"failed","output":f"Не удалось запустить background task: {failed_task.get('error')}"}
        return {"success":True,"task_id":task_id,"status":task.get("status","running"),"goal":goal,"output":f"Background task {task_id} запущен."}
    def cancel(self,task_id,reason="Cancelled by user"):
        task_id=str(task_id); emit_task=None
        with self._lock:
            task=self._tasks.get(task_id)
            if task is None:return {"success":False,"error":"task_not_found","task_id":task_id}
            if task.get("status") in _TERMINAL_STATUSES:return {"success":False,"error":"task_not_active","task_id":task_id,"status":task.get("status")}
            future=self._futures.get(task_id)
            if future is not None and future.cancel():
                task["status"]="cancelled";task["error"]=str(reason);task["finished_at"]=datetime.now().isoformat(timespec="seconds");self._futures.pop(task_id,None);self._save();emit_task=dict(task)
            else:task["status"]="cancelling";task["error"]=str(reason);self._save()
        if emit_task is not None:
            self._emit("task.cancelled",self._event_payload(emit_task,error=emit_task.get("error")),task=emit_task);return {"success":True,"task_id":task_id,"status":"cancelled"}
        from agent_runtime import get_agent_runtime
        get_agent_runtime().cancel(task_id);return {"success":True,"task_id":task_id,"status":"cancelling","output":"Отмена запрошена. Текущий безопасный шаг завершится, следующий не начнётся."}
    def _run(self,task_id):
        event_type=event_payload=event_task=None
        try:
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None or task.get("status") in {"cancelled","cancelling"}:
                    if task is not None and task.get("status")=="cancelling":
                        task["status"]="cancelled";task["finished_at"]=datetime.now().isoformat(timespec="seconds");self._save();event_type="task.cancelled";event_payload=self._event_payload(task,error=task.get("error"));event_task=dict(task)
                    return None
                goal=task["goal"];session_id=task["session_id"]
            from agent_runtime import get_agent_runtime
            result=get_agent_runtime().run(goal,session_id=session_id,mode="background",task_id=task_id)
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None:return None
                if task.get("status")=="cancelling":
                    task["status"]="cancelled";task["finished_at"]=datetime.now().isoformat(timespec="seconds");event_type="task.cancelled";event_payload=self._event_payload(task,error=task.get("error"));event_task=dict(task);self._save()
                elif task.get("status")!="cancelled":
                    task["status"]="completed";task["result"]=str(result);task["finished_at"]=datetime.now().isoformat(timespec="seconds");task["error"]=None;self._save();event_type="task.completed";event_payload=self._event_payload(task,result=str(result));event_task=dict(task)
        except Exception as error:
            try:
                from agent_runtime import ExecutionCancelled;cancelled=isinstance(error,ExecutionCancelled)
            except Exception:cancelled=False
            with self._lock:
                task=self._tasks.get(task_id)
                if task is None or task.get("status")=="cancelled":return None
                if cancelled or task.get("status")=="cancelling":
                    task["status"]="cancelled";task["finished_at"]=datetime.now().isoformat(timespec="seconds");event_type="task.cancelled";event_payload=self._event_payload(task,error=task.get("error") or "Cancelled");event_task=dict(task);self._save()
                else:
                    task["status"]="failed";task["error"]=str(error);task["result"]=None;task["finished_at"]=datetime.now().isoformat(timespec="seconds");task["traceback"]=traceback.format_exc()[-4000:];self._save();event_type="task.failed";event_payload=self._event_payload(task,error=str(error));event_task=dict(task)
        finally:
            with self._lock:self._futures.pop(task_id,None);self._save()
            if event_type is not None:self._emit(event_type,event_payload,task=event_task)
        return None if event_type in {"task.cancelled","task.failed"} else (event_payload or {}).get("result")
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
        if status in _TERMINAL_STATUSES:return {"success":False,"ready":True,"task_id":task_id,"error":task.get("error"),"status":status,"output":f"Background task {status}: {task.get('error') or ''}"}
        return {"success":True,"ready":False,"task_id":task_id,"status":status,"output":f"Task {task_id} ещё выполняется."}


    def pause_task(self, task_id):
        """Pause a task without losing its persisted state."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        if task.get("status") != "running":
            return {
                "success": False,
                "error": (
                    f"Cannot pause task in status: "
                    f"{task.get('status')}"
                ),
            }

        task["status"] = "paused"
        task["paused"] = True

        if hasattr(self, "_save"):
            self._save()

        return {
            "success": True,
            "task_id": task_id,
            "status": "paused",
        }

    def resume_task(self, task_id):
        """Resume a previously paused task."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        if task.get("status") != "paused":
            return {
                "success": False,
                "error": (
                    f"Cannot resume task in status: "
                    f"{task.get('status')}"
                ),
            }

        task["status"] = "running"
        task["paused"] = False

        if hasattr(self, "_save"):
            self._save()

        return {
            "success": True,
            "task_id": task_id,
            "status": "running",
        }

    def recover_incomplete_tasks(self):
        """Mark interrupted running tasks as paused after restart."""
        recoverable = []

        for task_id, task in self.tasks.items():
            status = task.get("status")

            if status not in {"running", "paused"}:
                continue

            if status == "running":
                task["status"] = "paused"
                task["interrupted"] = True

            recoverable.append({
                "task_id": task_id,
                "goal": (
                    task.get("goal")
                    or task.get("description")
                    or task.get("task")
                ),
                "status": task.get("status"),
            })

        if hasattr(self, "_save"):
            self._save()

        return recoverable


    def add_task_artifact(
        self,
        task_id,
        artifact,
        artifact_type="result",
        name=None,
    ):
        """Attach a durable artifact to an existing task."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        artifacts = task.setdefault("artifacts", [])

        entry = {
            "type": artifact_type,
            "value": artifact,
        }

        if name is not None:
            entry["name"] = name

        artifacts.append(entry)

        if hasattr(self, "_save"):
            self._save()

        return {
            "success": True,
            "task_id": task_id,
            "artifact": entry,
        }

    def get_task_artifacts(self, task_id):
        """Return all durable artifacts attached to a task."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        return {
            "success": True,
            "task_id": task_id,
            "artifacts": list(task.get("artifacts", [])),
        }

    def set_task_result(self, task_id, result):
        """Persist the primary result of a task."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        task["result"] = result

        if hasattr(self, "_save"):
            self._save()

        return {
            "success": True,
            "task_id": task_id,
            "result": result,
        }


    def get_task_context(self, task_id):
        """Return durable context for continuing a task."""
        task = self.tasks.get(task_id)

        if task is None:
            return {
                "success": False,
                "error": f"Unknown task: {task_id}",
            }

        return {
            "success": True,
            "task_id": task_id,
            "goal": (
                task.get("goal")
                or task.get("description")
                or task.get("task")
            ),
            "status": task.get("status"),
            "result": task.get("result"),
            "artifacts": list(task.get("artifacts", [])),
            "parent_task_id": task.get("parent_task_id"),
            "interrupted": task.get("interrupted", False),
        }

    def find_related_task(self, text=None, task_id=None):
        """Find an explicit parent task or the most recent unfinished task."""
        if task_id:
            task = self.tasks.get(task_id)
            if task is not None:
                return {
                    "success": True,
                    "task_id": task_id,
                    "match": "explicit",
                }

        candidates = []

        for candidate_id, task in self.tasks.items():
            if task.get("status") in {"completed", "failed", "cancelled"}:
                continue

            goal = (
                task.get("goal")
                or task.get("description")
                or task.get("task")
                or ""
            )

            score = 0

            if text and isinstance(text, str):
                words = {
                    word.lower()
                    for word in text.split()
                    if len(word) > 2
                }
                goal_words = {
                    word.lower()
                    for word in str(goal).split()
                    if len(word) > 2
                }
                score = len(words & goal_words)

            candidates.append((score, candidate_id, task))

        if not candidates:
            return {
                "success": False,
                "reason": "no_related_task",
            }

        candidates.sort(key=lambda item: item[0], reverse=True)
        score, candidate_id, _ = candidates[0]

        return {
            "success": True,
            "task_id": candidate_id,
            "match": "semantic" if score else "active",
            "score": score,
        }

    def build_continuation_context(self, text=None, task_id=None):
        """Build context for a request that may continue previous work."""
        related = self.find_related_task(
            text=text,
            task_id=task_id,
        )

        if not related.get("success"):
            return {
                "success": True,
                "continuation": False,
                "context": None,
            }

        context = self.get_task_context(related["task_id"])

        return {
            "success": True,
            "continuation": True,
            "match": related.get("match"),
            "context": context,
        }
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
