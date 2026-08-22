\
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationResult:
    status: str
    verified: bool
    retry_recommended: bool = False
    reason: str | None = None
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "status": self.status,
            "verified": self.verified,
            "retry_recommended": self.retry_recommended,
            "reason": self.reason,
            "evidence": self.evidence,
        }


class OutcomeVerifier:
    """
    Проверяет фактический результат действия.

    Источники доказательств:
    - результат инструмента;
    - состояние до/после;
    - пользовательская или агентная функция проверки.
    """

    SUCCESS_STATUSES = {"success", "completed", "done", "ok"}

    def _tool_success(self, result):
        if result is None:
            return None

        if isinstance(result, bool):
            return result

        if isinstance(result, dict):
            if "success" in result:
                return bool(result["success"])

            status = str(result.get("status", "")).lower()
            if status:
                return status in self.SUCCESS_STATUSES

        return None

    def verify(
        self,
        goal=None,
        tool_result=None,
        before=None,
        after=None,
        check=None,
    ):
        evidence = {
            "goal": goal,
            "tool_result": tool_result,
            "state_changed": (
                before != after
                if before is not None and after is not None
                else None
            ),
        }

        if callable(check):
            try:
                checked = check(
                    goal=goal,
                    tool_result=tool_result,
                    before=before,
                    after=after,
                )
            except TypeError:
                checked = check()

            if isinstance(checked, dict):
                verified = checked.get("verified")

                if verified is None:
                    verified = checked.get("success")

                if verified is True:
                    return VerificationResult(
                        status="verified",
                        verified=True,
                        reason=checked.get("reason"),
                        evidence={**evidence, "check": checked},
                    )

                if verified is False:
                    return VerificationResult(
                        status="failed",
                        verified=False,
                        retry_recommended=True,
                        reason=checked.get(
                            "reason",
                            "Verification check failed",
                        ),
                        evidence={**evidence, "check": checked},
                    )

            if checked is True:
                return VerificationResult(
                    status="verified",
                    verified=True,
                    evidence=evidence,
                )

            if checked is False:
                return VerificationResult(
                    status="failed",
                    verified=False,
                    retry_recommended=True,
                    reason="Verification check failed",
                    evidence=evidence,
                )

        tool_success = self._tool_success(tool_result)

        if tool_success is False:
            return VerificationResult(
                status="failed",
                verified=False,
                retry_recommended=True,
                reason="Tool reported failure",
                evidence=evidence,
            )

        if before is not None and after is not None:
            if before != after:
                return VerificationResult(
                    status="verified",
                    verified=True,
                    evidence=evidence,
                )

            if tool_success is True:
                return VerificationResult(
                    status="uncertain",
                    verified=False,
                    retry_recommended=False,
                    reason=(
                        "Tool reported success, but observable "
                        "state did not change"
                    ),
                    evidence=evidence,
                )

        if tool_success is True:
            return VerificationResult(
                status="reported_success",
                verified=False,
                retry_recommended=False,
                reason=(
                    "Tool reported success, but there is no "
                    "independent verification"
                ),
                evidence=evidence,
            )

        return VerificationResult(
            status="unknown",
            verified=False,
            retry_recommended=False,
            reason="Insufficient evidence to verify outcome",
            evidence=evidence,
        )


def verify_outcome(
    goal=None,
    tool_result=None,
    before=None,
    after=None,
    check=None,
):
    return OutcomeVerifier().verify(
        goal=goal,
        tool_result=tool_result,
        before=before,
        after=after,
        check=check,
    ).to_dict()
