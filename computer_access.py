"""Exclusive ownership of the shared Mac across an agent turn.

Read-only reasoning and filesystem work may run concurrently. A turn retains
ownership after its first desktop action so another task cannot change the
screen while the model reasons about its previous observation.
"""
from contextlib import contextmanager
from threading import RLock

from execution_context import current_execution, raise_if_execution_cancelled

_DESKTOP = RLock()
_DESKTOP_MODULES = {
    'capabilities.apps', 'capabilities.gui', 'capabilities.key',
    'capabilities.observe', 'capabilities.browser', 'capabilities.shell',
    'spotify_control', 'youtube', 'tools',
}


@contextmanager
def desktop_access(tool_name):
    from tool_registry import TOOL_REGISTRY
    definition = next((item for item in TOOL_REGISTRY if item.name == tool_name), None)
    if definition is None or definition.implementation_module not in _DESKTOP_MODULES:
        yield
        return
    context = current_execution()
    if context is not None and context._desktop_owned:
        raise_if_execution_cancelled()
        yield
        return
    while True:
        raise_if_execution_cancelled()
        if _DESKTOP.acquire(timeout=0.05):
            break
    try:
        raise_if_execution_cancelled()
        if context is not None:
            context._desktop_owned = True
        yield
    finally:
        if context is None or not context._desktop_owned:
            _DESKTOP.release()


def release_desktop(context):
    if context._desktop_owned:
        context._desktop_owned = False
        _DESKTOP.release()
