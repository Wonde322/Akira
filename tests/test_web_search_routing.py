import pytest
from types import SimpleNamespace
from test_native_open_flow import response


@pytest.mark.parametrize('query', ['погугли', 'загугли королевский 17', 'найди в интернете', 'search the web'])
def test_search_exposes_existing_browser_tools_within_budget(query):
    from capabilities.tool_router import select_tool_schemas
    from tool_registry import get_tool_schemas
    selected = select_tool_schemas(query, get_tool_schemas(), limit=6)
    names = {s['function']['name'] for s in selected}
    assert {'web_search', 'discover_capability'} <= names
    assert len(selected) <= 6


def test_search_followup_keeps_topic_and_runs_browser_without_gui_plan(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    permissions = isolated_project('permissions')
    permissions.set_confirmation_provider(lambda *args: True)
    session = loop.get_session('web-followup')
    session.add({'role': 'user', 'content': 'кто такой королевский 17'})
    session.add({'role': 'assistant', 'content': 'Нужно проверить источники.'})
    replies = iter([
        response(name='web_search', args={'query': 'королевский 17'}),
        response('Результаты поиска: https://example.com/source'),
    ])
    requests, actions = [], []
    def create(**kwargs):
        requests.append(kwargs)
        assert {'web_search'} <= {s['function']['name'] for s in kwargs['tools']}
        assert len(kwargs['tools']) <= 6
        return next(replies)
    def implementation(name):
        def execute(**kwargs):
            actions.append((name, kwargs))
            return {'success': True, 'output': 'Источник https://example.com/source'}
        return execute
    monkeypatch.setattr(loop, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, 'get_tool_implementation', implementation)
    monkeypatch.setattr(loop, 'build_memory_context', lambda *args, **kwargs: '')
    monkeypatch.setattr(loop, '_inject_observation', lambda *args, **kwargs: pytest.fail('No GUI screenshot for browser reading'))
    result = loop.ask('погугли', session_id='web-followup')
    assert 'https://example.com/source' in result
    assert [name for name, _ in actions] == ['web_search']
    assert any(m.get('content') == 'кто такой королевский 17' for m in requests[0]['messages'])
    assert session.task is None
