import json
from types import SimpleNamespace

import pytest


def response(content=None, name=None, args=None):
    calls = [SimpleNamespace(id='native-call', function=SimpleNamespace(name=name, arguments=json.dumps(args or {})))] if name else None
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls))])


@pytest.mark.parametrize('nickname', ['спотик', 'спотифай'])
def test_native_open_needs_no_gui_plan_or_screenshot(isolated_project, monkeypatch, nickname):
    loop = isolated_project('agent_loop')
    apps = isolated_project('capabilities.apps')
    permissions = isolated_project('permissions')
    permissions.set_confirmation_provider(lambda *a: True)
    from computer_state import Application
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    monkeypatch.setattr(apps._resolver, '_cache', [Application('Spotify', '/Applications/Spotify.app', 'com.spotify.client')])
    commands, requests = [], []
    monkeypatch.setattr(apps.subprocess, 'run', lambda args, **kw: commands.append(args) or SimpleNamespace(returncode=0))
    responses = iter([response(name='open', args={'target': nickname}), response('Открыл Spotify.')])
    def create(**kwargs):
        requests.append(kwargs)
        assert len(kwargs['tools']) <= 6
        assert 'open' in {schema['function']['name'] for schema in kwargs['tools']}
        return next(responses)
    monkeypatch.setattr(loop, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, 'build_memory_context', lambda *a, **k: '')
    monkeypatch.setattr(loop, '_inject_observation', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Native open must not request a screenshot')))
    session = loop.get_session('native-open')
    session.add({'role': 'user', 'content': 'Какая сейчас громкость?'})
    session.add({'role': 'assistant', 'content': 'Громкость 100%.'})
    session.add({'role': 'user', 'content': 'сделай тише'})
    session.add({'role': 'assistant', 'content': 'Громкость 90%.'})
    result = AkiraGateway(AgentRuntime()).submit_text('открой ' + nickname, metadata={'session_id': 'native-open'})
    assert result == 'Открыл Spotify.'
    assert commands == [['open', '-a', 'Spotify']]
    assert len(requests) == 2
    assert loop.get_session('native-open').task is None


def test_discovery_pins_native_tool_without_creating_a_gui_task(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    actions = []
    responses = iter([
        response(name='discover_capability', args={'query': 'громкость'}),
        response(name='get_volume'), response('Громкость 90%.'),
    ])
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        if len(requests) == 2:
            assert 'get_volume' in {s['function']['name'] for s in kwargs['tools']}
        return next(responses)
    def implementation(name):
        if name == 'discover_capability':
            return lambda **kw: {'success': True, 'data': {'tools': [{'name': 'get_volume'}]}}
        return lambda **kw: actions.append(name) or {'success': True, 'output': '90%'}
    monkeypatch.setattr(loop, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, 'build_memory_context', lambda *a, **k: '')
    monkeypatch.setattr(loop, 'get_permission', lambda name: 'auto')
    monkeypatch.setattr(loop, 'get_tool_implementation', implementation)
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    assert AkiraGateway(AgentRuntime()).submit_text('проверь это', metadata={'session_id': 'native-discovery'}) == 'Громкость 90%.'
    assert actions == ['get_volume']
    assert loop.get_session('native-discovery').task is None


def test_status_callback_reaches_model_wait_without_leaking_into_metadata(monkeypatch):
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    from execution_context import report_execution_status
    statuses = []
    def execute(*a, **k):
        report_execution_status('Лимит модели: жду 3 с')
        return 'done'
    gateway = AkiraGateway(AgentRuntime(executor=execute), on_status=statuses.append)
    assert gateway.submit_text('test') == 'done'
    assert statuses == ['Лимит модели: жду 3 с']


def test_repeated_native_failure_stops_instead_of_consuming_more_requests(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        assert len(calls) <= 2
        return response(name='open', args={'target': 'MissingApp'})
    monkeypatch.setattr(loop, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, 'build_memory_context', lambda *a, **k: '')
    monkeypatch.setattr(loop, 'get_permission', lambda name: 'auto')
    monkeypatch.setattr(loop, 'get_tool_implementation', lambda name: lambda **kw: {'success': False, 'error': 'open_failed', 'data': 'Приложение не найдено'})
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    result = AkiraGateway(AgentRuntime()).submit_text('open MissingApp')
    assert 'Приложение не найдено' in result
    assert len(calls) == 2


def test_native_permission_denial_is_terminal_without_another_model_call(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        assert len(calls) == 1
        return response(name='write', args={'path': 'file.txt', 'text': 'test'})
    monkeypatch.setattr(loop, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, 'build_memory_context', lambda *a, **k: '')
    monkeypatch.setattr(loop, 'get_permission', lambda name: 'confirm')
    monkeypatch.setattr(loop, 'request_confirmation', lambda *a: False)
    monkeypatch.setattr(loop, 'get_tool_implementation', lambda name: lambda **kw: (_ for _ in ()).throw(AssertionError('Denied action executed')))
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    assert 'не разрешил' in AkiraGateway(AgentRuntime()).submit_text('write file')
    assert len(calls) == 1
