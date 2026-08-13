import importlib
import sys
import types

import pytest


PROJECT_MODULES = {
    "analysis",
    "brain",
    "file_tools",
    "goal_analysis",
    "memory",
    "permissions",
    "proactive",
    "spotify_control",
    "tools",
}


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
        return importlib.import_module(module_name)

    yield load

    for name in PROJECT_MODULES:
        sys.modules.pop(name, None)
