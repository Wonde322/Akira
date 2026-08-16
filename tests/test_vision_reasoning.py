"""Тесты обработки reasoning-ответа vision-модели (qwen3.6-27b).

Покрывают:
- удаление  thinking... response из ответа;
- response только с  thinking → неуспех;
- finish_reason=stop / length;
- length без финального текста → retry с увеличенным max_tokens;
- retry не дал финального текста → VisionUnavailable;
- отсутствие CoT в Observation;
- ограничение длины description;
- vision failure → безопасный fallback без падения.
"""

import types

import pytest

from backend_fakes import FakeBackend, FakeVisionProvider


class _Choice:
    def __init__(self, content, finish_reason):
        self.message = types.SimpleNamespace(content=content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content, finish_reason):
        self.choices = [_Choice(content, finish_reason)]


class FakeCompletions:
    """Повторяет интерфейс client.chat.completions.create с заранее
    заданной очередью ответов."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = types.SimpleNamespace(
            completions=FakeCompletions(responses)
        )


def _describe(isolated_project, monkeypatch, tmp_path, responses, prompt="промпт"):
    vision = isolated_project("capabilities.vision")
    config = isolated_project("config")

    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    # Не трогаем compress_image: в тестах он не нужен (изображение не читается).
    monkeypatch.setattr(vision, "compress_image", lambda path: str(path))

    client = FakeClient(responses)

    def call():
        return vision.describe_image(client, str(image), prompt, model="qwen/test")

    return call, vision, config, client


def _stop(content):
    return _Response(content, "stop")


def _length(content):
    return _Response(content, "length")


# ---------- extract_final_text ----------

def test_extract_final_text_strips_thinking_block(isolated_project):
    vision = isolated_project("capabilities.vision")

    content = "<think>\nlong reasoning\n</think>\nНа экране браузер."

    assert vision.extract_final_text(content) == "На экране браузер."


def test_extract_final_text_only_thinking_returns_empty(isolated_project):
    vision = isolated_project("capabilities.vision")

    assert vision.extract_final_text("<think>\nразмышления") == ""
    assert vision.extract_final_text("<think>\nразмышления\n</think>") == ""


def test_extract_final_text_without_reasoning_is_unchanged(isolated_project):
    vision = isolated_project("capabilities.vision")

    assert vision.extract_final_text("в браузере открыт сайт") == "в браузере открыт сайт"


def test_extract_final_text_multiple_blocks(isolated_project):
    vision = isolated_project("capabilities.vision")

    content = "<think>\nпервое\n</think>\n<think>\nвторое\n</think>\nИтог."

    assert vision.extract_final_text(content) == "Итог."


# ---------- describe_image / retry ----------

def test_describe_think_plus_final_text(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_stop("<think>\nкот\n</think>\nНа экране браузер.")],
    )

    assert call() == "На экране браузер."
    assert len(client.chat.completions.calls) == 1
    assert client.chat.completions.calls[0]["max_tokens"] == config.VISION_MAX_TOKENS


def test_describe_only_thinking_is_failure(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_stop("<think>\nтолько размышления")],
    )

    with pytest.raises(vision.VisionUnavailable):
        call()


def test_describe_stop_without_thinking(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_stop("в браузере открыт сайт")],
    )

    assert call() == "в браузере открыт сайт"


def test_describe_length_with_final_text_no_retry(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_length("<think>\nкот\n</think>\nНа экране терминал.")],
    )

    assert call() == "На экране терминал."
    assert len(client.chat.completions.calls) == 1


def test_describe_length_without_final_text_retries(
    isolated_project, monkeypatch, tmp_path
):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [
            _length("<think>\nкот оборвался"),
            _stop("<think>\nвторой заход\n</think>\nФинальное описание."),
        ],
    )

    assert call() == "Финальное описание."
    assert len(client.chat.completions.calls) == 2
    assert client.chat.completions.calls[0]["max_tokens"] == config.VISION_MAX_TOKENS
    assert client.chat.completions.calls[1]["max_tokens"] == config.VISION_RETRY_TOKENS


def test_describe_retry_fails_raises_vision_unavailable(
    isolated_project, monkeypatch, tmp_path
):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [
            _length("<think>\nкот оборвался"),
            _length("<think>\nснова только кот"),
        ],
    )

    with pytest.raises(vision.VisionUnavailable):
        call()

    assert len(client.chat.completions.calls) == 2


# ---------- description length limit ----------

def test_description_length_is_limited(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_stop("<think>\nдумаю длинно\n</think>" + "x" * 5000)],
    )

    result = call()

    assert len(result) == config.VISION_MAX_DESCRIPTION_CHARS
    assert result.endswith("…")


def test_short_description_not_truncated(isolated_project, monkeypatch, tmp_path):
    call, vision, config, client = _describe(
        isolated_project, monkeypatch, tmp_path,
        [_stop("короткое описание")],
    )

    assert call() == "короткое описание"


# ---------- CoT не попадает в Observation / fallback ----------

def test_no_cot_in_observation(isolated_project, monkeypatch, tmp_path):
    observe = isolated_project("capabilities.observe")
    vision = isolated_project("capabilities.vision")

    monkeypatch.setattr(observe, "backend", FakeBackend())
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)

    client = FakeClient(
        [_stop("<think>\nкот\n</think>\nНа экране браузер с сайтом.")]
    )
    provider = vision.VisionProvider(client, "qwen/test")
    monkeypatch.setattr(vision, "provider", provider)

    result = observe.observe(interpret=True)

    assert result["success"] is True
    assert result["metadata"]["interpreted"] is True
    assert result["data"]["interpretation"] == "На экране браузер с сайтом."
    assert " thinking" not in result["data"]["interpretation"]


def test_no_cot_via_fake_provider_is_passed_through(isolated_project, monkeypatch, tmp_path):
    observe = isolated_project("capabilities.observe")
    vision = isolated_project("capabilities.vision")

    monkeypatch.setattr(observe, "backend", FakeBackend())
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(
        vision, "provider", FakeVisionProvider(description="описание экрана")
    )

    result = observe.observe(interpret=True)

    assert result["success"] is True
    assert result["data"]["interpretation"] == "описание экрана"


def test_vision_failure_is_safe_fallback(
    isolated_project, monkeypatch, tmp_path
):
    observe = isolated_project("capabilities.observe")
    vision = isolated_project("capabilities.vision")

    monkeypatch.setattr(observe, "backend", FakeBackend())
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)

    client = FakeClient(
        [
            _length("<think>\nобрыв"),
            _length("<think>\nснова обрыв"),
        ]
    )
    provider = vision.VisionProvider(client, "qwen/test")
    monkeypatch.setattr(vision, "provider", provider)

    result = observe.observe(interpret=True)

    assert result["success"] is True
    assert result["metadata"]["interpreted"] is False
    assert result["data"]["interpretation"] is None
    assert "interpretation_error" in result["data"]