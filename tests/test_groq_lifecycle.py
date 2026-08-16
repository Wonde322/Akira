import importlib
import sys
import types

import pytest


def _clear_modules():
    for name in (
        "config", "brain", "analysis", "permissions", "memory",
        "tool_registry", "session", "audit", "format",
    ):
        sys.modules.pop(name, None)


def test_brain_and_analysis_import_without_groq_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    _clear_modules()

    brain = importlib.import_module("brain")
    analysis = importlib.import_module("analysis")

    try:
        assert brain.client is None
        assert analysis.client is None
    finally:
        _clear_modules()


def test_create_groq_client_requires_env_only_at_call_time(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    _clear_modules()

    fake_groq = types.ModuleType("groq")
    fake_groq.Groq = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    config = importlib.import_module("config")

    try:
        with pytest.raises(KeyError):
            config.create_groq_client()

        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        client = config.create_groq_client()
        assert client == {"api_key": "test-key"}
    finally:
        _clear_modules()


def test_lazy_client_is_shared_across_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    _clear_modules()

    fake_groq = types.ModuleType("groq")

    class FakeGroq:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_groq.Groq = FakeGroq
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    brain = importlib.import_module("brain")
    analysis = importlib.import_module("analysis")
    config = importlib.import_module("config")

    try:
        assert brain._ensure_client() is config._client
        assert analysis._ensure_client() is config._client
        assert brain.client is analysis.client
    finally:
        _clear_modules()