"""Единый слой конфигурации Akira."""

import os
import subprocess
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
GROQ_API_KEY_ENV = "GROQ_API_KEY"
MODEL = "openai/gpt-oss-120b"
MAX_HISTORY = 12
MAX_TOOL_ITERATIONS = 128
MAX_TURN_PERSISTED = 16
MEMORY_FILE = str(PROJECT_ROOT / "memory.json")
PERMISSIONS_FILE = str(PROJECT_ROOT / "permissions.json")
SPOTIFY_TOKEN_FILE = str(PROJECT_ROOT / "spotify_token.json")
LOG_DIR = PROJECT_ROOT / "logs"

MAX_READ_BYTES = 200_000
MAX_FIND_LIMIT = 50
DEFAULT_SHELL_TIMEOUT = 30
MAX_SHELL_TIMEOUT = 120
MAX_SHELL_OUTPUT_CHARS = 4000
MAX_WAIT_SECONDS = 60
SCREENSHOT_DIR = LOG_DIR / "screenshots"

MAX_TYPE_LENGTH = 20_000
MAX_CLICKS = 10
MAX_SCROLL_AMOUNT = 50
MAX_DRAG_DURATION = 5.0

VISION_MODEL = "qwen/qwen3.6-27b"
VISION_API_KEY_ENV = "VISION_API_KEY"
REASONING_VISION = False
VISION_MAX_SIDE = 1440
VISION_MAX_IMAGE_BYTES = 1_500_000
VISION_MAX_TOKENS = 2000
VISION_RETRY_TOKENS = 4000
VISION_MAX_DESCRIPTION_CHARS = 2000

TTS_VOICE = "Milena"

COMPUTER_USE_MAX_STEPS = 100
MAX_ACTIONS_WITHOUT_OBSERVE = 8
NO_PROGRESS_LIMIT = 3
MAX_OBSERVATION_HISTORY = 8

COMPUTER_USE_TOOLS = (
    "open", "close", "click", "select", "type", "scroll", "drag", "key", "observe", "wait",
    "find", "read", "write", "create", "move", "copy", "rename", "delete", "shell",
    "plan_task", "update_task_plan", "complete_plan_step", "fail_plan_step", "verify_goal",
    "finish_task", "discover_capability",
    "background_task_start", "background_task_status", "background_task_result",
)

# Only these operations require visual evidence after execution. Process,
# filesystem and shell operations carry their own authoritative evidence and
# must not trigger a screenshot merely to prove that they worked.
STATE_CHANGING_TOOLS = (
    "click", "select", "type", "scroll", "drag", "key",
)

_client = None
_client_lock = threading.Lock()


def _get_groq_api_key():
    return os.environ.get(GROQ_API_KEY_ENV)


def create_groq_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from groq import Groq
                api_key = _get_groq_api_key()
                if not api_key:
                    raise KeyError(GROQ_API_KEY_ENV)
                _client = Groq(api_key=api_key)
    return _client

BACKGROUND_TASK_MAX_CONCURRENT = 3
BACKGROUND_TASK_MAX_STORED = 100
BACKGROUND_TASK_DIR = PROJECT_ROOT / "runtime" / "tasks"
BACKGROUND_TASK_FILE = PROJECT_ROOT / "runtime" / "background_tasks.json"
