"""
Central execution safety gate.

Uses the existing PermissionManager; does not create a second
permission system.
"""

from permissions import PermissionManager


class ExecutionSafetyGate:
    def __init__(self, permission_manager=None):
        self.permissions = (
            permission_manager
            if permission_manager is not None
            else PermissionManager()
        )

    def check(self, tool_name, arguments=None):
        arguments = arguments or {}

        for method_name in (
            "get_permission",
            "get_level",
            "check",
            "can_execute",
        ):
            method = getattr(self.permissions, method_name, None)

            if not callable(method):
                continue

            try:
                result = method(tool_name)
            except TypeError:
                try:
                    result = method(tool_name, arguments)
                except Exception as exc:
                    return {
                        "allowed": False,
                        "requires_confirmation": False,
                        "reason": str(exc),
                    }
            except Exception as exc:
                return {
                    "allowed": False,
                    "requires_confirmation": False,
                    "reason": str(exc),
                }

            if isinstance(result, dict):
                level = (
                    result.get("level")
                    or result.get("permission")
                    or result.get("status")
                )

                allowed = result.get("allowed")
                if allowed is None:
                    allowed = level not in {"blocked", "deny", "denied"}

                return {
                    "allowed": bool(allowed),
                    "requires_confirmation": level in {
                        "ask", "confirm", "confirmation"
                    },
                    "level": level,
                    "reason": result.get("reason"),
                }

            if isinstance(result, bool):
                return {
                    "allowed": result,
                    "requires_confirmation": False,
                    "level": None,
                }

            if isinstance(result, str):
                level = result.lower()
                return {
                    "allowed": level not in {"blocked", "deny", "denied"},
                    "requires_confirmation": level in {
                        "ask", "confirm", "confirmation"
                    },
                    "level": result,
                }

        return {
            "allowed": False,
            "requires_confirmation": False,
            "reason": "No compatible permission check method",
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
