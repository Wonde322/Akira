import importlib
import sys
import types

import pytest


PROJECT_MODULES = {
    "activity_stats",
    "analysis",
    "audit",
    "brain",
    "capabilities.apps",
    "capabilities.backend",
    "capabilities.filesystem",
    "capabilities.gui",
    "capabilities.key",
    "capabilities.observe",
    "capabilities.observation",
    "capabilities.protocol",
    "capabilities.shell",
    "capabilities.task",
    "capabilities.vision",
    "capabilities.wait",
    "config",
    "format",
    "memory",
    "permissions",
    "session",
    "spotify_control",
    "tool_registry",
    "tools",
    "youtube",
}


@pytest.fixture(autouse=True)
def reset_proactive_singletons():
    """Keep persistent proactive state from leaking between independent tests.

    Proactive interruption mode and attention budget intentionally persist in the
    application, but a previous test must not be able to leave the shared default
    singletons in quiet/focus mode or with an exhausted budget for the next test.
    Individual tests can still verify persistence by constructing stores with an
    explicit path or by exercising multiple operations within the same test.
    """
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
    """Import project modules in an isolated working directory.

    The production code currently resolves its JSON files relative to CWD.
    Keeping every import in ``tmp_path`` prevents tests from reading or writing
    the user's real memory and permission files.
    """
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
