"""Central execution safety gate.

Uses the existing PermissionManager; does not create a second permission system.
"""

from config import PERMISSIONS_FILE
from permissions import PermissionManager


class ExecutionSafetyGate:
    def __init__(self, permission_manager=None):
        self.permissions = (
            permission_manager
            if permission_manager is not None
            else PermissionManager(PERMISSIONS_FILE)
        )

    def check(self, tool_name, arguments=None):
        arguments = arguments or {}
        level = self.permissions.get_permission(tool_name)

        if level == "blocked":
            return {
                "allowed": False,
                "requires_confirmation": False,
                "level": level,
                "reason": "Tool is blocked by permissions.",
            }

        if level == "confirm":
            return {
                "allowed": True,
                "requires_confirmation": True,
                "level": level,
                "reason": "User confirmation required.",
            }

        return {
            "allowed": True,
            "requires_confirmation": False,
            "level": "auto",
        }

    def authorize(self, tool_name, arguments=None, confirmed=False):
        decision = self.check(tool_name, arguments)

        if not decision["allowed"]:
            return {
                "authorized": False,
                "reason": decision.get("reason") or "Permission denied",
                **decision,
            }

        if decision["requires_confirmation"] and not confirmed:
            return {
                "authorized": False,
                "reason": "User confirmation required",
                **decision,
            }

        return {
            "authorized": True,
            **decision,
        }
