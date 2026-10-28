import sys
from types import SimpleNamespace


def test_search_returns_bounded_source_text_without_browser(monkeypatch):
    from capabilities.web import web_search
    calls = []
    class Search:
        def __init__(self, **kwargs):
            assert kwargs['timeout'] == 10
        def text(self, query, **kwargs):
            calls.append(query)
            return [{'title': 'Источник', 'href': 'https://example.com', 'body': 'Ответ ' * 500}]
    monkeypatch.setitem(sys.modules, 'ddgs', SimpleNamespace(DDGS=Search))
    result = web_search('Кто это?')
    assert result['success']
    assert result['data']['results'][0]['url'] == 'https://example.com'
    assert len(result['data']['results'][0]['snippet']) <= 700
    assert calls == ['Кто это?']


def test_search_errors_are_reported_not_hidden(monkeypatch):
    from capabilities.web import web_search
    class Search:
        def __init__(self, **kwargs):
            raise RuntimeError('Network timeout')
    monkeypatch.setitem(sys.modules, 'ddgs', SimpleNamespace(DDGS=Search))
    assert web_search('topic')['error'] == 'web_search_failed'
    assert web_search('')['error'] == 'invalid_query'
