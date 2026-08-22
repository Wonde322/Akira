"""Универсальное выполнение команд в оболочке macOS.

Политика: по умолчанию требует подтверждения (никогда не auto).
"""

import os
import signal
import subprocess

from config import DEFAULT_SHELL_TIMEOUT, MAX_SHELL_OUTPUT_CHARS, MAX_SHELL_TIMEOUT
from .filesystem import CapabilityError, resolve_path
from .protocol import fail, ok


def _truncate_output(text):
    if len(text) <= MAX_SHELL_OUTPUT_CHARS:
        return text, False
    return text[:MAX_SHELL_OUTPUT_CHARS], True


def _run(command, timeout, working_dir):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=working_dir, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        process.wait()
        return {"timeout": True, "exit_code": None, "stdout": "", "stderr": "Команда убита по таймауту."}
    return {"timeout": False, "exit_code": process.returncode, "stdout": stdout or "", "stderr": stderr or ""}


def shell(command, timeout=None, cwd=None):
    if not isinstance(command, str) or not command.strip():
        return fail("invalid_command", "command должен быть непустой строкой.")
    if timeout is None:
        timeout = DEFAULT_SHELL_TIMEOUT
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_SHELL_TIMEOUT:
        return fail("invalid_timeout", "timeout должен быть числом от 1 до " + str(MAX_SHELL_TIMEOUT) + ".")
    working_dir = None
    if cwd is not None:
        try:
            working_dir = str(resolve_path(cwd, require_existing=True, must_be_dir=True))
        except CapabilityError as error:
            return fail(error.code, str(error))
    try:
        outcome = _run(command, timeout, working_dir)
    except Exception as error:
        return fail("execution_error", str(error))
    if outcome["timeout"]:
        return fail("timeout", "Команда превысила лимит времени.", timeout_seconds=int(timeout), killed=True)
    stdout, stdout_truncated = _truncate_output(outcome["stdout"])
    stderr, stderr_truncated = _truncate_output(outcome["stderr"])
    metadata = {"truncated": stdout_truncated or stderr_truncated, "stdout_truncated": stdout_truncated, "stderr_truncated": stderr_truncated}
    data = {"exit_code": outcome["exit_code"], "stdout": stdout, "stderr": stderr}
    if outcome["exit_code"] != 0:
        return fail("nonzero_exit", data, **metadata)
    return ok(data, **metadata)
