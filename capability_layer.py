
"""Universal capability abstraction for Akira.

Brain should reason in semantic operations:

    observe
    open
    close
    find
    create
    read
    write
    move
    copy
    rename
    delete
    select
    click
    type
    key
    scroll
    drag
    wait
    verify
    execute

The capability layer resolves those operations to the best
available concrete tool.

Concrete adapters remain independent:

    GUI
    Browser
    Filesystem
    Shell
    Applications

This module intentionally contains routing logic, not LLM logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


# ============================================================
# Capability model
# ============================================================


@dataclass(frozen=True)
class Capability:
    name: str
    operation: str
    modality: str
    tool: str
    priority: int = 100
    requires_target: bool = False


# Lower priority number = preferred route.
#
# The important part is that Brain can ask for:
#
#     click
#
# rather than:
#
#     browser_click
#
# or:
#
#     click
#
# directly.

CAPABILITIES = (
    # --------------------------------------------------------
    # Observation
    # --------------------------------------------------------

    Capability(
        "observe",
        "observe",
        "desktop",
        "observe",
        10,
    ),

    # --------------------------------------------------------
    # Open / close
    # --------------------------------------------------------

    Capability(
        "open",
        "open",
        "desktop",
        "open",
        10,
    ),

    # --------------------------------------------------------
    # Find
    # --------------------------------------------------------

    Capability(
        "find",
        "find",
        "universal",
        "find",
        10,
    ),

    # --------------------------------------------------------
    # Files / content
    #
    # These names are the ACTUAL current registry names.
    # --------------------------------------------------------

    Capability(
        "read",
        "read",
        "filesystem",
        "read",
        10,
    ),

    Capability(
        "write",
        "write",
        "filesystem",
        "write",
        10,
    ),

    Capability(
        "move",
        "move",
        "filesystem",
        "move",
        10,
    ),

    Capability(
        "rename",
        "rename",
        "filesystem",
        "rename",
        10,
    ),

    # --------------------------------------------------------
    # Selection / interaction
    # --------------------------------------------------------

    Capability(
        "select",
        "select",
        "desktop",
        "select",
        10,
    ),

    Capability(
        "click",
        "click",
        "desktop",
        "click",
        10,
        True,
    ),

    Capability(
        "type",
        "type",
        "desktop",
        "type",
        10,
        True,
    ),

    Capability(
        "key",
        "key",
        "desktop",
        "key",
        10,
    ),

    Capability(
        "scroll",
        "scroll",
        "desktop",
        "scroll",
        10,
    ),

    # --------------------------------------------------------
    # Waiting / verification
    # --------------------------------------------------------

    Capability(
        "wait",
        "wait",
        "universal",
        "wait",
        10,
    ),

    Capability(
        "verify",
        "verify",
        "universal",
        "verify_goal",
        10,
    ),

    # --------------------------------------------------------
    # Shell
    # --------------------------------------------------------

    Capability(
        "execute",
        "execute",
        "shell",
        "shell",
        10,
    ),

    # --------------------------------------------------------
    # Existing higher-level capabilities
    # --------------------------------------------------------

    Capability(
        "plan",
        "plan",
        "universal",
        "plan_task",
        10,
    ),

    Capability(
        "memory",
        "memory",
        "universal",
        "remember_memory",
        10,
    ),

    # Browser modality:
    # opening a URL is implemented by browser_navigate.
    Capability(
        "browser_open",
        "open",
        "browser",
        "browser_navigate",
        10,
    ),

    # Browser modality:
    # current browser state is exposed through browser_current.
    Capability(
        "browser_observe",
        "observe",
        "browser",
        "browser_current",
        10,
    ),

    # Browser click is implemented through the
    # existing browser DOM adapter.
    Capability(
        "browser_click",
        "click",
        "browser",
        "browser_click",
        10,
    ),

    # Browser type is implemented through the
    # existing browser DOM adapter.
    Capability(
        "browser_type",
        "type",
        "browser",
        "browser_type",
        10,
    ),
)



# ============================================================
# Resolver
# ============================================================


class CapabilityResolver:
    """Resolve semantic operations to concrete tools."""

    def __init__(self):
        self._lock = threading.RLock()

        self._capabilities = tuple(
            sorted(
                CAPABILITIES,
                key=lambda item: (
                    item.operation,
                    item.priority,
                ),
            )
        )

        self._available_tools = set()

        self.refresh()

    def refresh(self):
        """Refresh available concrete tools from registry."""

        try:
            from tool_registry import (
                get_tool_schemas,
            )

            schemas = get_tool_schemas()

            names = set()

            for schema in schemas:

                try:
                    name = (
                        schema
                        .get("function", {})
                        .get("name")
                    )

                    if name:
                        names.add(name)

                except Exception:
                    continue

            with self._lock:
                self._available_tools = names

        except Exception:

            with self._lock:
                self._available_tools = set()

        return self.snapshot()

    def snapshot(self):

        with self._lock:

            return {
                "available_tools": sorted(
                    self._available_tools
                ),
                "capabilities": [
                    {
                        "name": item.name,
                        "operation": item.operation,
                        "modality": item.modality,
                        "tool": item.tool,
                        "priority": item.priority,
                    }
                    for item in self._capabilities
                    if (
                        item.tool
                        in self._available_tools
                    )
                ],
            }

    # ========================================================
    # Resolution
    # ========================================================

    def resolve(
        self,
        operation,
        modality=None,
        preferred_tool=None,
    ):
        operation = str(
            operation or ""
        ).strip()

        modality = (
            str(modality).strip()
            if modality is not None
            else None
        )

        preferred_tool = (
            str(preferred_tool).strip()
            if preferred_tool is not None
            else None
        )

        with self._lock:

            candidates = [
                item
                for item in self._capabilities
                if (
                    item.operation == operation
                    and item.tool
                    in self._available_tools
                )
            ]

        if modality:

            matching_modality = [
                item
                for item in candidates
                if item.modality == modality
            ]

            if matching_modality:
                candidates = matching_modality

        if preferred_tool:

            matching_tool = [
                item
                for item in candidates
                if item.tool == preferred_tool
            ]

            if matching_tool:
                candidates = matching_tool

        if not candidates:

            return {
                "success": False,
                "error": "capability_unavailable",
                "operation": operation,
                "modality": modality,
                "output": (
                    f"Capability '{operation}' "
                    "недоступна."
                ),
            }

        selected = sorted(
            candidates,
            key=lambda item: item.priority,
        )[0]

        return {
            "success": True,
            "operation": operation,
            "modality": selected.modality,
            "tool": selected.tool,
            "capability": selected.name,
            "priority": selected.priority,
            "fallbacks": [
                item.tool
                for item in sorted(
                    candidates,
                    key=lambda item: item.priority,
                )[1:]
            ],
        }

    def candidates(
        self,
        operation,
        modality=None,
    ):

        with self._lock:

            candidates = [
                item
                for item in self._capabilities
                if (
                    item.operation == operation
                    and item.tool
                    in self._available_tools
                )
            ]

        if modality:

            candidates = [
                item
                for item in candidates
                if item.modality == modality
            ]

        candidates.sort(
            key=lambda item: item.priority
        )

        return [
            {
                "name": item.name,
                "operation": item.operation,
                "modality": item.modality,
                "tool": item.tool,
                "priority": item.priority,
            }
            for item in candidates
        ]


_resolver = None
_resolver_lock = threading.Lock()


def get_capability_resolver():

    global _resolver

    if _resolver is None:

        with _resolver_lock:

            if _resolver is None:
                _resolver = (
                    CapabilityResolver()
                )

    return _resolver


def resolve_capability(
    operation,
    modality=None,
    preferred_tool=None,
):
    return get_capability_resolver().resolve(
        operation,
        modality=modality,
        preferred_tool=preferred_tool,
    )


def capability_candidates(
    operation,
    modality=None,
):
    return get_capability_resolver().candidates(
        operation,
        modality=modality,
    )


def capability_snapshot():
    return get_capability_resolver().snapshot()


# ============================================================
# Universal execution facade
# ============================================================


def execute_capability(
    operation,
    arguments=None,
    modality=None,
    preferred_tool=None,
):
    """Resolve a semantic capability and execute its tool.

    This is intentionally a thin facade. The actual concrete
    implementation remains in tool_registry.
    """

    arguments = (
        arguments
        if isinstance(arguments, dict)
        else {}
    )

    resolution = resolve_capability(
        operation,
        modality=modality,
        preferred_tool=preferred_tool,
    )

    if not resolution.get("success"):
        return resolution

    tool_name = resolution["tool"]

    try:
        from tool_registry import (
            get_tool_implementation,
        )

        implementation = (
            get_tool_implementation(
                tool_name
            )
        )

    except Exception as error:

        return {
            "success": False,
            "error": "capability_implementation_error",
            "output": str(error),
            "resolution": resolution,
        }

    if implementation is None:

        return {
            "success": False,
            "error": "tool_implementation_missing",
            "tool": tool_name,
            "resolution": resolution,
            "output": (
                f"Implementation for {tool_name} "
                "не найдена."
            ),
        }

    try:

        result = implementation(
            **arguments
        )

    except TypeError as error:

        return {
            "success": False,
            "error": "capability_arguments_error",
            "tool": tool_name,
            "output": str(error),
            "resolution": resolution,
        }

    except Exception as error:

        return {
            "success": False,
            "error": "capability_execution_error",
            "tool": tool_name,
            "output": str(error),
            "resolution": resolution,
        }

    if isinstance(result, dict):

        result.setdefault(
            "capability",
            resolution["capability"],
        )

        result.setdefault(
            "resolved_tool",
            tool_name,
        )

        result.setdefault(
            "modality",
            resolution["modality"],
        )

    return result
