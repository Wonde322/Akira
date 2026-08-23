\
from dataclasses import dataclass, field
from typing import Any

@dataclass
class VerificationResult:
    status: str
    verified: bool
    retry_recommended: bool=False
    reason: str|None=None
    evidence: dict=field(default_factory=dict)
    def to_dict(self): return {"status":self.status,"verified":self.verified,"retry_recommended":self.retry_recommended,"reason":self.reason,"evidence":self.evidence}

class OutcomeVerifier:
    SUCCESS_STATUSES={"success","completed","done","ok"}
    AUTHORITATIVE_SOURCES={"process_state","filesystem_state","command_result"}

    def _tool_success(self,result):
        if result is None: return None
        if isinstance(result,bool): return result
        if isinstance(result,dict):
            if "success" in result: return bool(result["success"])
            status=str(result.get("status","")).lower()
            if status: return status in self.SUCCESS_STATUSES
        return None

    def _authoritative_source(self,result):
        if not isinstance(result,dict): return None
        data=result.get("data") if isinstance(result.get("data"),dict) else result
        source=data.get("verification") if isinstance(data,dict) else None
        return source if source in self.AUTHORITATIVE_SOURCES else None

    def verify(self,goal=None,tool_result=None,before=None,after=None,check=None):
        evidence={"goal":goal,"tool_result":tool_result,"state_changed":before!=after if before is not None and after is not None else None}
        if callable(check):
            try: checked=check(goal=goal,tool_result=tool_result,before=before,after=after)
            except TypeError: checked=check()
            if isinstance(checked,dict):
                verified=checked.get("verified",checked.get("success"))
                if verified is True: return VerificationResult("verified",True,reason=checked.get("reason"),evidence={**evidence,"check":checked})
                if verified is False: return VerificationResult("failed",False,True,checked.get("reason","Verification check failed"),{**evidence,"check":checked})
            if checked is True: return VerificationResult("verified",True,evidence=evidence)
            if checked is False: return VerificationResult("failed",False,True,"Verification check failed",evidence)
        tool_success=self._tool_success(tool_result)
        if tool_success is False: return VerificationResult("failed",False,True,"Tool reported failure",evidence)
        source=self._authoritative_source(tool_result)
        if tool_success is True and source:
            return VerificationResult("verified",True,False,f"Verified by {source}",{**evidence,"verification_source":source})
        if before is not None and after is not None:
            if before!=after: return VerificationResult("verified",True,evidence=evidence)
            if tool_success is True: return VerificationResult("uncertain",False,False,"Tool reported success, but observable state did not change",evidence)
        if tool_success is True: return VerificationResult("reported_success",False,False,"Tool reported success, but there is no independent verification",evidence)
        return VerificationResult("unknown",False,False,"Insufficient evidence to verify outcome",evidence)

def verify_outcome(goal=None,tool_result=None,before=None,after=None,check=None):
    return OutcomeVerifier().verify(goal=goal,tool_result=tool_result,before=before,after=after,check=check).to_dict()
