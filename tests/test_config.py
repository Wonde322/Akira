import sys


def test_config_exposes_the_expected_constants(isolated_project):
    config = isolated_project("config")

    assert config.PROJECT_ROOT.is_absolute()
    assert config.GROQ_API_KEY_ENV == "GROQ_API_KEY"
    assert config.MAX_HISTORY >= 1
    assert config.MAX_TOOL_ITERATIONS >= 1

    for path in (
        config.MEMORY_FILE,
        config.PERMISSIONS_FILE,
        config.SPOTIFY_TOKEN_FILE,
    ):
        assert str(config.PROJECT_ROOT) in path

    assert config.LOG_DIR.is_absolute()


def test_create_groq_client_is_lazy(monkeypatch, tmp_path):
    import importlib

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    sys.modules.pop("config", None)
    sys.modules.pop("groq", None)

    import types

    module = importlib.import_module("config")

    try:
        assert "groq" not in sys.modules

        class FakeGroq:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                FakeGroq.instances.append(self)

        monkeypatch.setitem(sys.modules, "groq", types.ModuleType("groq"))
        sys.modules["groq"].Groq = FakeGroq

        client = module.create_groq_client()

        assert isinstance(client, FakeGroq)
        assert client.kwargs == {"api_key": "test-key", "timeout": 30.0, "max_retries": 0}
    finally:
        sys.modules.pop("config", None)
        sys.modules.pop("groq", None)

def test_default_runtime_ignores_checkout_state(tmp_path):
    import json, os, subprocess
    script = '''
import json
from pathlib import Path
Path.home = staticmethod(lambda: Path(__import__('sys').argv[1]))
import config
from proactive_inbox import ProactiveInbox
print(json.dumps({'directory': str(config.RUNTIME_DIR), 'source': str(config.PROJECT_ROOT / 'runtime'), 'items': ProactiveInbox().list()}))
'''
    env = dict(os.environ)
    env.pop('AKIRA_RUNTIME_DIR', None)
    env.pop('XDG_STATE_HOME', None)
    env.pop('LOCALAPPDATA', None)
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], env=env, capture_output=True, text=True, check=True, timeout=10)
    state = json.loads(result.stdout)
    assert state['directory'] != state['source']
    assert str(tmp_path) in state['directory']
    assert state['items'] == []
