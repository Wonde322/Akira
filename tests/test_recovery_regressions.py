from capabilities.recovery import classify_failure


def test_structured_failure_data_is_preserved_for_recovery():
    result = classify_failure("write", {"success": False, "error": "permission", "data": "access denied"})
    assert result["output"] == "access denied"
    assert result["force_observe"] is True


def test_truthy_non_boolean_success_is_not_treated_as_success():
    result = classify_failure("click", {"success": "true", "error": "execution_error", "output": "bad"})
    assert result["failed"] is True
