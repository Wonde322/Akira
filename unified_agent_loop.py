\
from dataclasses import dataclass, field
from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "blocked"}
SYSTEM_VERIFIED_ACTIONS = {"open", "close", "read", "write", "create", "move", "copy", "rename", "delete", "shell", "find"}

@dataclass
class AgentStep:
    iteration: int
    decision: Any = None
    action: str | None = None
    arguments: dict = field(default_factory=dict)
    authorization: Any = None
    result: Any = None
    verification: Any = None
    observation_before: Any = None
    observation_after: Any = None

class UnifiedAgentLoop:
    """Host-owned loop; observation is visual evidence, not universal truth."""
    def __init__(self, brain=None, safety=None, verifier=None, recovery=None, observer=None, executor=None, planner=None, max_iterations=20):
        self.brain=brain; self.safety=safety; self.verifier=verifier; self.recovery=recovery; self.observer=observer; self.executor=executor; self.planner=planner; self.max_iterations=max_iterations

    def _observe(self):
        if not callable(self.observer): return None
        try: return self.observer()
        except Exception as exc: return {"success":False,"error":str(exc),"source":"observation"}

    def _normalize_decision(self, decision):
        if decision is None: return {"type":"finish","answer":None}
        if isinstance(decision,str): return {"type":"finish","answer":decision}
        if not isinstance(decision,dict): return {"type":"finish","answer":decision}
        normalized=dict(decision); action=normalized.get("action") or normalized.get("tool") or normalized.get("tool_name")
        if action:
            normalized.update(type="action",action=action,arguments=normalized.get("arguments") or normalized.get("args") or {}); return normalized
        status=str(normalized.get("status") or normalized.get("type") or "").lower()
        if status in {"finish","final","completed","complete","done","answer"}: normalized["type"]="finish"; return normalized
        normalized["type"]="finish"; return normalized

    def _decide(self, goal, state):
        if self.brain is None: return {"type":"finish","status":"failed","error":"Brain subsystem unavailable"}
        context={"goal":goal,"iteration":state["iteration"],"observation":state["observation"],"history":state["history"],"recovery":state.get("recovery")}
        for method_name in ("decide","next_action","agent_step"):
            method=getattr(self.brain,method_name,None)
            if callable(method):
                try: return self._normalize_decision(method(goal,context=context))
                except TypeError:
                    try: return self._normalize_decision(method(context))
                    except TypeError: continue
        for method_name in ("ask","run","handle","process"):
            method=getattr(self.brain,method_name,None)
            if callable(method):
                try: return self._normalize_decision(method(goal))
                except TypeError:
                    try: return self._normalize_decision(method(goal,context=context))
                    except TypeError: continue
        return {"type":"finish","status":"failed","error":"No supported brain entry point"}

    def _authorize(self, action, arguments):
        if self.safety is None: return {"authorized":True,"reason":"No safety gate configured"}
        method=getattr(self.safety,"authorize",None)
        if not callable(method): return {"authorized":True,"reason":"Safety adapter unavailable"}
        try: return method(action,arguments,confirmed=False)
        except TypeError: return method(action,arguments)

    def _execute(self, action, arguments):
        if not callable(self.executor): return {"success":False,"error":"No tool executor configured","action":action}
        try: return self.executor(action,arguments)
        except TypeError:
            try: return self.executor(action=action,arguments=arguments)
            except Exception as exc: return {"success":False,"error":str(exc),"action":action}
        except Exception as exc: return {"success":False,"error":str(exc),"action":action}

    def _needs_observation(self, action, result):
        if str(action).lower() not in SYSTEM_VERIFIED_ACTIONS: return True
        if not isinstance(result,dict): return False
        data=result.get("data") if isinstance(result.get("data"),dict) else result
        return data.get("verification") not in {"process_state","filesystem_state","command_result"}

    def _verify(self, goal, result, before, after):
        if self.verifier is None:
            return {"status":"reported_success" if isinstance(result,dict) and result.get("success") else "unknown","verified":bool(isinstance(result,dict) and result.get("success"))}
        method=getattr(self.verifier,"verify",None)
        if not callable(method): return {"status":"unknown","verified":False,"reason":"Verifier has no verify method"}
        try: verification=method(goal=goal,tool_result=result,before=before,after=after)
        except Exception as exc: return {"status":"unknown","verified":False,"reason":str(exc)}
        return verification.to_dict() if hasattr(verification,"to_dict") else verification

    def _recover(self, action, arguments, error):
        if self.recovery is None: return None
        record=getattr(self.recovery,"record_failure",None)
        if callable(record):
            try: record(action,arguments,error=error)
            except Exception: pass
        context=getattr(self.recovery,"recovery_context",None)
        if callable(context):
            try: return context()
            except Exception: return None
        return None

    def run(self, goal):
        state={"goal":goal,"iteration":0,"history":[],"observation":self._observe(),"recovery":None}
        while state["iteration"]<self.max_iterations:
            state["iteration"]+=1; before=state["observation"]; decision=self._decide(goal,state)
            if decision.get("type")=="finish":
                status=str(decision.get("status","completed")).lower(); status=status if status in TERMINAL_STATUSES else "completed"
                return {"success":status=="completed","status":status,"answer":decision.get("answer") or decision.get("response") or decision.get("result"),"iterations":state["iteration"],"history":state["history"]}
            action=decision.get("action"); arguments=decision.get("arguments") or {}; step=AgentStep(iteration=state["iteration"],decision=decision,action=action,arguments=arguments,observation_before=before)
            authorization=self._authorize(action,arguments); step.authorization=authorization
            if not authorization.get("authorized",False):
                step.result={"success":False,"error":authorization.get("reason") or "Action not authorized"}; state["history"].append(self._step_dict(step))
                if authorization.get("requires_confirmation",False): return {"success":False,"status":"awaiting_confirmation","action":action,"arguments":arguments,"iterations":state["iteration"],"history":state["history"]}
                state["recovery"]=self._recover(action,arguments,step.result["error"]); continue
            result=self._execute(action,arguments); step.result=result
            after=self._observe() if self._needs_observation(action,result) else None; step.observation_after=after
            verification=self._verify(goal,result,before,after); step.verification=verification; state["history"].append(self._step_dict(step))
            if after is not None: state["observation"]=after
            tool_failed=isinstance(result,dict) and result.get("success") is False
            verification_failed=isinstance(verification,dict) and verification.get("status")=="failed"
            if tool_failed or verification_failed:
                error=result.get("error") if isinstance(result,dict) else None
                if error is None and isinstance(verification,dict): error=verification.get("reason")
                state["recovery"]=self._recover(action,arguments,error); continue
            state["recovery"]=None
            verified=bool(verification.get("verified",False)) if isinstance(verification,dict) else False
            if verified and decision.get("complete_after_action",False): return {"success":True,"status":"completed","iterations":state["iteration"],"history":state["history"]}
        return {"success":False,"status":"budget_exhausted","iterations":state["iteration"],"history":state["history"]}

    @staticmethod
    def _step_dict(step):
        return {"iteration":step.iteration,"decision":step.decision,"action":step.action,"arguments":step.arguments,"authorization":step.authorization,"result":step.result,"verification":step.verification,"observation_before":step.observation_before,"observation_after":step.observation_after}
