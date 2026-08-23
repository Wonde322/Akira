from config import MAX_SHELL_OUTPUT_CHARS


def _shell(isolated_project):
    return isolated_project("capabilities.shell").shell


def test_shell_captures_stdout_and_exit_code(isolated_project):
    result = _shell(isolated_project)("printf 'hello'")
    assert result["success"] is True
    assert result["data"]["exit_code"] == 0
    assert result["data"]["stdout"] == "hello"
    assert result["data"]["stderr"] == ""


def test_shell_reports_nonzero_exit_code(isolated_project):
    result = _shell(isolated_project)("exit 3")
    assert result["success"] is False
    assert result["error"] == "nonzero_exit"
    assert result["data"]["exit_code"] == 3


def test_shell_captures_stderr(isolated_project):
    result = _shell(isolated_project)("printf 'boom' 1>&2")
    assert result["data"]["stderr"] == "boom"
    assert result["data"]["stdout"] == ""


def test_shell_truncates_large_output(isolated_project):
    result = _shell(isolated_project)("yes | head -c 5000")
    assert result["success"] is True
    assert result["metadata"]["truncated"] is True
    assert len(result["data"]["stdout"]) == MAX_SHELL_OUTPUT_CHARS


def test_shell_timeout_kills_process(isolated_project):
    result = _shell(isolated_project)("sleep 5", timeout=1)
    assert result["success"] is False
    assert result["error"] == "timeout"
    assert result["metadata"]["killed"] is True


def test_shell_rejects_invalid_timeout(isolated_project):
    shell = _shell(isolated_project)
    assert shell("echo hi", timeout=0)["error"] == "invalid_timeout"
    assert shell("echo hi", timeout=999)["error"] == "invalid_timeout"
    assert shell("echo hi", timeout="x")["error"] == "invalid_timeout"


def test_shell_rejects_empty_command(isolated_project):
    shell = _shell(isolated_project)
    assert shell("")["error"] == "invalid_command"
    assert shell("   ")["error"] == "invalid_command"
    assert shell(42)["error"] == "invalid_command"


def test_shell_honors_cwd_within_home(isolated_project, monkeypatch, tmp_path):
    import capabilities.filesystem as filesystem
    shell = _shell(isolated_project)
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    result = shell("pwd", cwd=str(tmp_path))
    assert result["success"] is True
    assert result["data"]["stdout"].strip() == str(tmp_path)


def test_shell_rejects_cwd_outside_home(isolated_project, monkeypatch, tmp_path):
    import capabilities.filesystem as filesystem
    shell = _shell(isolated_project)
    monkeypatch.setattr(filesystem, "HOME", tmp_path)
    assert shell("pwd", cwd=str(tmp_path.parent))["error"] == "not_allowed"


def test_shell_default_policy_is_confirm_in_registry(isolated_project):
    registry = isolated_project("tool_registry")
    assert registry.get_default_tool_permissions()["shell"] == "confirm"
