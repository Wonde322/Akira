import importlib
import sys
import types

import pytest


PROJECT_MODULES = {
    "activity_stats", "analysis", "audit", "brain", "capabilities.apps",
    "capabilities.backend", "capabilities.filesystem", "capabilities.gui",
    "capabilities.key", "capabilities.observe", "capabilities.observation",
    "capabilities.protocol", "capabilities.shell", "capabilities.task",
    "capabilities.vision", "capabilities.wait", "config", "format", "memory",
    "permissions", "session", "spotify_control", "tool_registry", "tools", "youtube",
}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_proactive_singletons():
    try:
        from proactive_interruption_control import get_proactive_interruption_control
        get_proactive_interruption_control().reset()
    except Exception:
        pass
    try:
        from proactive_attention_budget import get_proactive_attention_budget
        get_proactive_attention_budget().reset()
    except Exception:
        pass
    yield
    try:
        from proactive_interruption_control import get_proactive_interruption_control
        get_proactive_interruption_control().reset()
    except Exception:
        pass
    try:
        from proactive_attention_budget import get_proactive_attention_budget
        get_proactive_attention_budget().reset()
    except Exception:
        pass


@pytest.fixture
def isolated_project(monkeypatch, tmp_path):
    for name in PROJECT_MODULES:
        sys.modules.pop(name, None)

    fake_groq = types.ModuleType("groq")

    class FakeGroq:
        def __init__(self, *args, **kwargs):
            pass

    fake_groq.Groq = FakeGroq
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    def load(module_name):
        module = importlib.import_module(module_name)
        permissions_module = sys.modules.get("permissions")
        if permissions_module is not None:
            permissions_module.PERMISSIONS_FILE = str(tmp_path / "permissions.json")
        memory_module = sys.modules.get("memory")
        if memory_module is not None:
            memory_module.MEMORY_FILE = str(tmp_path / "memory.json")
        audit_module = sys.modules.get("audit")
        if audit_module is not None:
            audit_module.AUDIT_FILE = str(tmp_path / "tool_audit.jsonl")
        return module

    yield load

    for name in PROJECT_MODULES:
        sys.modules.pop(name, None)
