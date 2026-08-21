"""Compatibility facade for Akira's agent runtime.

The implementation formerly living in this module now lives in ``agent_loop``.
Keeping this module as an alias preserves existing imports and monkeypatching
behaviour while making the runtime module the owner of reasoning, tool calls,
recovery, verification and session-backed agent execution.

``brain`` historically had module-local mutable state (client/session/history),
and the test/runtime lifecycle may unload ``brain`` without unloading
``agent_loop``. Reload the implementation when the compatibility facade is
imported so a new ``brain`` lifecycle receives fresh state and current
project-module dependencies instead of inheriting a stale loop instance.
"""
import importlib as _importlib
import sys as _sys
import agent_loop as _agent_loop

_agent_loop = _importlib.reload(_agent_loop)

# Preserve module identity for legacy callers: ``import brain`` and
# ``import agent_loop`` resolve to the same implementation object.
_sys.modules[__name__] = _agent_loop
