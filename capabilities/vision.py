"""Абстракция передачи изображения vision-провайдеру (model-agnostic).

Brain и capabilities не знают конкретный vision model ID. Vision-провайдер
инкапсулирует клиент и модель; перед отправкой снимок сжимается (sips),
чтобы не передавать огромный Retina PNG.

- Отдельная vision-модель (qwen/qwen3.6-27b через Groq).
- text fallback без vision (VISION_MODEL=None → VisionUnavailable).
- В будущем — multimodal reasoning-модель (REASONING_VISION=True в config).

Vision failure никогда не роняет Akira: observe превращает его в обычный
fallback-результат.
"""

import base64
import os
import re
import subprocess
import tempfile

from config import (
    MODEL,
    VISION_MAX_DESCRIPTION_CHARS,
    VISION_MAX_SIDE,
    VISION_MAX_TOKENS,
    VISION_RETRY_TOKENS,
)

_REASONING_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class VisionUnavailable(Exception):
    """Vision-провайдер не сконфигурирован или недоступен."""


# Инжектируемый провайдер (тесты подменяют на FakeVisionProvider).
provider = None


def extract_final_text(content):
    """Возвращает финальный текст ответа vision-модели без reasoning-блоков.

    qwen3.6-27b — reasoning-модель и отвечает в формате
    ``<think>...</think> <финальный ответ>``. Возвращается только текст после
    последнего ``</think>``. Если ответ — только reasoning (в т.ч. обрезанный
    по max_tokens), возвращается ''.
    """
    if not content:
        return ""

    if "<think>" not in content:
        return content.strip()

    marker = content.rfind("</think>")

    if marker == -1:
        return ""

    tail = _REASONING_BLOCK.sub("", content[marker + len("</think>"):]).strip()

    if "<think>" in tail:
        return ""

    return tail


def limit_description(text, max_chars=VISION_MAX_DESCRIPTION_CHARS):
    """Ограничивает длину итогового описания, чтобы не раздувать контекст."""
    if not text:
        return text

    if len(text) <= max_chars:
        return text

    return text[: max_chars - 1] + "…"


def _complete(client, model, message, max_tokens):
    return client.chat.completions.create(
        model=model,
        messages=message,
        max_tokens=max_tokens,
    )


def _final_text(response):
    return extract_final_text(response.choices[0].message.content or "")


def _describe_with_retry(client, model, message):
    """Запрашивает описание с обработкой reasoning-ответа и finish_reason.

    - финальный текст есть → вернуть его (stop или length с ответом);
    - нет финального текста и finish_reason=length → один retry с увеличенным
      max_tokens (CoT занял весь бюджет);
    - retry снова не дал финального текста → VisionUnavailable;
    - нет финального текста при stop (только <think>) → VisionUnavailable.
    """
    response = _complete(client, model, message, VISION_MAX_TOKENS)
    text = _final_text(response)

    if text:
        return limit_description(text)

    finish_reason = (response.choices[0].finish_reason or "").lower()

    if finish_reason == "length":
        response = _complete(client, model, message, VISION_RETRY_TOKENS)
        text = _final_text(response)

        if text:
            return limit_description(text)

    raise VisionUnavailable(
        "Vision-модель не вернула финальное описание "
        "(reasoning-only/truncated, finish=" + finish_reason + ")."
    )


def _mime_for(path):
    extension = os.path.splitext(path)[1].lower()

    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }.get(extension, "image/png")


def build_vision_message(image_path, prompt):
    """Собирает user-сообщение с текстом и изображением (data URI)."""
    with open(image_path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")

    data_uri = "data:" + _mime_for(image_path) + ";base64," + encoded

    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]


def compress_image(path, max_side=VISION_MAX_SIDE):
    """Сжимает снимок через sips (встроен в macOS, без новых зависимостей).

    Возвращает путь к временному файлу. Если сжатие не удалось, возвращает
    исходный путь (отправка оригинала, а не ошибка).
    """
    try:
        _, out_path = tempfile.mkstemp(suffix=".jpeg")
        result = subprocess.run(
            [
                "sips",
                "--resampleHeightWidthMax",
                str(max_side),
                "-s",
                "format",
                "jpeg",
                str(path),
                "--out",
                out_path,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0 or not os.path.exists(out_path):
            return path

        return out_path
    except Exception:
        return path


class VisionProvider:
    """Обёртка клиент + vision-модель. Brain/капабилити не знают model ID."""

    def __init__(self, client, model):
        self._client = client
        self._model = model

    def describe(self, image_path, prompt):
        compressed = compress_image(image_path)
        message = build_vision_message(compressed, prompt)

        return _describe_with_retry(self._client, self._model, message)


def get_provider():
    """Возвращает сконфигурированный vision-провайдер или None."""
    if provider is not None:
        return provider

    from config import VISION_MODEL, create_groq_client

    if not VISION_MODEL:
        return None

    return VisionProvider(create_groq_client(), VISION_MODEL)


def describe_image(client, image_path, prompt, model=None):
    """Отправляет изображение и возвращает текстовое описание.

    model=None → используется сконфигурированный vision-провайдер.
    Может поднять исключение (VisionUnavailable / ошибка провайдера) —
    вызывающий код превращает это в fallback-результат.
    """
    if model is None:
        vision = get_provider()

        if vision is None:
            raise VisionUnavailable(
                "Vision-провайдер не сконфигурирован (VISION_MODEL не задан)."
            )

        return vision.describe(image_path, prompt)

    compressed = compress_image(image_path)
    message = build_vision_message(compressed, prompt)

    return _describe_with_retry(client, model, message)