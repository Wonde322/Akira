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

# Максимум сообщений одного хода (user + tool-активность + ответ),
# которые сохраняются в истории сессии. Ограничивает, чтобы длинный
# tool-loop не выталкивал исходный user message из окна контекста.
MAX_TURN_PERSISTED = 16

MEMORY_FILE = str(PROJECT_ROOT / "memory.json")
PERMISSIONS_FILE = str(PROJECT_ROOT / "permissions.json")
SPOTIFY_TOKEN_FILE = str(PROJECT_ROOT / "spotify_token.json")
LOG_DIR = PROJECT_ROOT / "logs"

# Capability layer
MAX_READ_BYTES = 200_000
MAX_FIND_LIMIT = 50
DEFAULT_SHELL_TIMEOUT = 30
MAX_SHELL_TIMEOUT = 120
MAX_SHELL_OUTPUT_CHARS = 4000
MAX_WAIT_SECONDS = 60
SCREENSHOT_DIR = LOG_DIR / "screenshots"

# GUI capability layer
MAX_TYPE_LENGTH = 20_000
MAX_CLICKS = 10
MAX_SCROLL_AMOUNT = 50
MAX_DRAG_DURATION = 5.0

# Vision / computer-use layer
# Отдельная vision-модель (не reasoning). None — только text fallback без vision.
VISION_MODEL = "qwen/qwen3.6-27b"
VISION_API_KEY_ENV = "VISION_API_KEY"
# True — только для будущей multimodal reasoning-модели; сейчас gpt-oss-120b text-only.
REASONING_VISION = False

# Сжатие снимков перед отправкой vision-провайдеру (sips, без новых зависимостей).
VISION_MAX_SIDE = 1440
VISION_MAX_IMAGE_BYTES = 1_500_000

# Vision reasoning-ответ: бюджет токенов, retry-бюджет и лимит финального описания.
# qwen3.6-27b — reasoning-модель: тратит токены на <think>. Бюджет должен
# покрывать CoT + финальный ответ, а retry даёт запас для длинного размышления.
VISION_MAX_TOKENS = 2000
VISION_RETRY_TOKENS = 4000
VISION_MAX_DESCRIPTION_CHARS = 2000

# Voice / TTS
# Голос озвучки macOS (`say -v`). Проверено: Milena (ru_RU) и Yuri (ru_RU).
TTS_VOICE = "Milena"

# Computer-use loop
COMPUTER_USE_MAX_STEPS = 100
MAX_ACTIONS_WITHOUT_OBSERVE = 8
NO_PROGRESS_LIMIT = 5
MAX_OBSERVATION_HISTORY = 8

# Инструменты, включающие computer-use режим, и state-changing (требуют observe).
COMPUTER_USE_TOOLS = (
    "open",
    "close",
    "click",
    "select",
    "type",
    "scroll",
    "drag",
    "key",
    "observe",
    "finish_task",
)
STATE_CHANGING_TOOLS = (
    "open",
    "close",
    "click",
    "select",
    "type",
    "scroll",
    "drag",
    "key",
)

_client = None
_client_lock = threading.Lock()


def _get_groq_api_key():
    """Получает Groq API key из environment или macOS Keychain."""
    key = os.environ.get(GROQ_API_KEY_ENV)
    if key:
        return key

    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                "Akira-Groq-API-Key",
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    key = result.stdout.strip()
    return key or None


def create_groq_client():
    """Возвращает единый лениво созданный Groq-клиент.

    Клиент создаётся один раз на процесс при первом обращении. Импорт
    модулей, которые используют этот клиент, не падает без GROQ_API_KEY:
    исключение возникнет только при фактическом LLM-запросе.
    """
    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                from groq import Groq

                _client = Groq(api_key=_get_groq_api_key())

    return _client

# Background autonomous task runtime.
BACKGROUND_TASK_MAX_CONCURRENT = 3
BACKGROUND_TASK_MAX_STORED = 100
BACKGROUND_TASK_DIR = PROJECT_ROOT / "runtime" / "tasks"
BACKGROUND_TASK_FILE = (
    PROJECT_ROOT
    / "runtime"
    / "background_tasks.json"
)
