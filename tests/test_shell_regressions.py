from capabilities import shell as shell_module


def test_nonzero_exit_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(
        shell_module,
        "_run",
        lambda command, timeout, working_dir: {
            "timeout": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "boom",
        },
    )

    result = shell_module.shell("false")

    assert result["success"] is False
    assert result["error"] == "nonzero_exit"
    assert result["data"] == {
        "exit_code": 2,
        "stdout": "",
        "stderr": "boom",
    }


def test_successful_exit_keeps_output_data(monkeypatch):
    monkeypatch.setattr(
        shell_module,
        "_run",
        lambda command, timeout, working_dir: {
            "timeout": False,
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
        },
    )

    result = shell_module.shell("echo ok")

    assert result["success"] is True
    assert result["data"]["stdout"] == "ok"
