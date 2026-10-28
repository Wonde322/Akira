import json
import pytest
from capabilities import browser


@pytest.mark.parametrize('action,args', [(browser.browser_click, {'selector': '#missing'}), (browser.browser_type, {'selector': '#missing', 'text': 'hello'})])
def test_missing_dom_target_is_a_failed_tool_result(monkeypatch, action, args):
    monkeypatch.setattr(browser, 'browser_execute', lambda *a, **k: {'success': True, 'value': {'success': False, 'error': 'element_not_found'}, 'output': 'missing'})
    result = action(**args)
    assert result['success'] is False
    assert result['error'] == 'element_not_found'


def test_browser_type_serializes_arbitrary_text_as_javascript_string(monkeypatch):
    expressions = []
    monkeypatch.setattr(browser, 'browser_execute', lambda expr, **k: expressions.append(expr) or {'success': True, 'value': {'success': True}})
    text = "'\\\nПривет\t💡"
    browser.browser_type('input[name="a"]', text)
    assert json.dumps(text) in expressions[0]
    assert 'setter.call' in expressions[0]


def test_javascript_exception_remains_a_tool_failure(monkeypatch):
    monkeypatch.setattr(browser, 'browser_execute', lambda *a, **k: {'success': False, 'error': 'javascript_error'})
    assert browser.browser_click('#target')['error'] == 'javascript_error'
