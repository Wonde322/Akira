from capabilities.protocol import is_structured, result_to_text


def test_malformed_structured_result_falls_back_to_legacy_error():
    result = {"success": False, "data": "detail", "metadata": []}
    assert not is_structured(result)
    assert result_to_text(result).startswith("ОШИБКА")


def test_success_must_be_boolean():
    assert not is_structured({"success": "true", "data": {}, "error": None, "metadata": {}})


def test_json_unfriendly_data_does_not_crash_text_conversion():
    assert result_to_text({"success": True, "data": {"value": {1, 2}}, "error": None, "metadata": {}})
