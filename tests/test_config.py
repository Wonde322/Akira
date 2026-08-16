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
        assert client.kwargs == {"api_key": "test-key"}
    finally:
        sys.modules.pop("config", None)
        sys.modules.pop("groq", None)