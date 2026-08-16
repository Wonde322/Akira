from capabilities.protocol import (
    data_to_text,
    fail,
    is_structured,
    ok,
    result_to_text,
)


def test_ok_and_fail_structures():
    assert ok({"a": 1}, flag=True) == {
        "success": True,
        "data": {"a": 1},
        "error": None,
        "metadata": {"flag": True},
    }

    assert fail("boom", "детали", code=7) == {
        "success": False,
        "data": "детали",
        "error": "boom",
        "metadata": {"code": 7},
    }


def test_is_structured_detects_protocol_but_not_legacy():
    assert is_structured(ok("x")) is True
    assert is_structured(fail("e")) is True
    assert is_structured({"success": True, "error": None, "output": "legacy"}) is False
    assert is_structured("raw") is False


def test_result_to_text_structured_success_serializes_data():
    text = result_to_text(ok({"path": "/x", "matches": [1, 2]}))

    assert '"path": "/x"' in text
    assert '"matches"' in text


def test_result_to_text_structured_failure_uses_detail():
    text = result_to_text(fail("timeout", "Команда превысила лимит."))

    assert text == "ОШИБКА (timeout): Команда превысила лимит."


def test_result_to_text_structured_failure_without_detail_is_empty_suffix():
    text = result_to_text(fail("blocked"))

    assert text == "ОШИБКА (blocked): "


def test_result_to_text_legacy_behaviour_is_preserved():
    assert result_to_text({"success": True, "error": None, "output": "ок"}) == "ок"
    assert result_to_text({"success": False, "error": "boom", "output": None}) == (
        "ОШИБКА (boom): "
    )


def test_data_to_text_handles_primitives_and_none():
    assert data_to_text(None) == ""
    assert data_to_text("строка") == "строка"
    assert data_to_text(42) == "42"
    assert data_to_text({"k": "v"}) == '{"k": "v"}'


def test_data_to_text_respects_limit():
    assert data_to_text("x" * 100, limit=10) == "x" * 10
    assert data_to_text("короткий", limit=10) == "короткий"
