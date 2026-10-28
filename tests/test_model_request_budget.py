import json
from types import SimpleNamespace
from threading import Event
import pytest

import model_requests
from capabilities.tool_router import select_tool_schemas


def schema(name):
    return {'type': 'function', 'function': {'name': name, 'description': name, 'parameters': {'type': 'object', 'properties': {}}}}


class ProviderError(RuntimeError):
    def __init__(self, status, text, body=None):
        super().__init__(text)
        self.status_code = status
        self.body = body or {}


def client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_low_confidence_never_expands_to_entire_registry():
    schemas = [schema('discover_capability')] + [schema('tool_' + str(i)) for i in range(80)]
    assert len(select_tool_schemas('сделай это', schemas, limit=12)) <= 12


def test_short_followup_keeps_volume_context_and_both_tools(isolated_project):
    loop = isolated_project('agent_loop')
    session = loop.get_session('followup-routing')
    session.add({'role': 'user', 'content': 'Какая сейчас громкость?'})
    session.add({'role': 'assistant', 'content': '94 процента'})
    session.add({'role': 'user', 'content': 'сделай 100'})
    tools = loop._tools_for_reasoning(session, 'сделай 100', False)
    names = {tool['function']['name'] for tool in tools}
    assert {'get_volume', 'set_volume'} <= names
    assert len(tools) <= 12
    assert len(loop.SYSTEM_PROMPT) < 2500


def test_rejected_missing_tool_is_re_advertised_not_executed():
    calls = []
    def create(**kwargs):
        calls.append(kwargs['tools'])
        if len(calls) == 1:
            raise ProviderError(400, "attempted to call tool 'get_volume' which was not in request.tools", {'failed_generation': json.dumps({'name': 'get_volume', 'arguments': {}})})
        return 'regenerated response'
    result = model_requests.create_completion(client(create), all_tools=[schema('get_volume')], tools=[schema('discover_capability')])
    assert result == 'regenerated response'
    assert len(calls) == 2
    assert calls[1][-1]['function']['name'] == 'get_volume'


def test_unknown_tool_never_gets_advertised_or_executed():
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        raise ProviderError(400, "attempted to call tool 'unknown' which was not in request.tools")
    with pytest.raises(ProviderError):
        model_requests.create_completion(client(create), all_tools=[schema('get_volume')], tools=[])
    assert len(calls) == 1


def test_throttling_waits_once_using_provider_time(monkeypatch):
    calls, waits = [], []
    monkeypatch.setattr(model_requests, '_wait', waits.append)
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ProviderError(429, 'Please try again in 1.1475s.')
        return 'ok'
    assert model_requests.create_completion(client(create), all_tools=[], tools=[]) == 'ok'
    assert waits == [pytest.approx(1.2475)]
    assert len(calls) == 2


def test_throttling_is_bounded_to_one_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(model_requests, '_wait', lambda _: None)
    def create(**kwargs):
        calls.append(kwargs)
        raise ProviderError(429, 'Please try again in 1s.')
    with pytest.raises(ProviderError):
        model_requests.create_completion(client(create), all_tools=[], tools=[])
    assert len(calls) == 2


def test_rate_wait_is_cancellable():
    from execution_context import ExecutionContext, ExecutionCancelled, activate_execution, deactivate_execution
    cancel = Event(); cancel.set()
    token = activate_execution(ExecutionContext('test', 'test', 'auto', _cancel_event=cancel))
    try:
        with pytest.raises(ExecutionCancelled):
            model_requests._wait(.5)
    finally:
        deactivate_execution(token)


def test_rate_limit_ui_does_not_dump_organization_or_provider_json():
    from desktop_app.worker import _friendly_error
    error = ProviderError(429, 'organization private-org; rate_limit_exceeded; Please try again in 1.1475s.')
    text = _friendly_error(error)
    assert '2 с.' in text
    assert 'private-org' not in text
    assert '429' not in text


def test_volume_followup_runs_with_contextual_schemas_and_small_output_budget(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    actions, calls = [], []
    def response(content=None, name=None, arguments=None):
        tool_calls = [SimpleNamespace(id='call', function=SimpleNamespace(name=name, arguments=json.dumps(arguments or {})))] if name else None
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])
    responses = iter([
        response(name='get_volume'), response('Громкость 94%.'),
        response(name='set_volume', arguments={'level': 100}), response('Громкость 100%.'),
    ])
    def create(**kwargs):
        calls.append(kwargs)
        assert kwargs['max_completion_tokens'] == 1024
        assert kwargs['reasoning_effort'] == 'low'
        assert len(kwargs['tools']) <= 12
        if len(calls) >= 3:
            assert {'set_volume', 'get_volume'} <= {s['function']['name'] for s in kwargs['tools']}
        return next(responses)
    monkeypatch.setattr(loop, 'client', client(create))
    monkeypatch.setattr(loop, 'build_memory_context', lambda *a, **k: '')
    monkeypatch.setattr(loop, 'get_permission', lambda name: 'auto')
    monkeypatch.setattr(loop, 'get_tool_implementation', lambda name: lambda **kw: actions.append((name, kw)) or {'success': True, 'output': 'ok'})
    from agent_runtime import AgentRuntime
    from akira_gateway import AkiraGateway
    gateway = AkiraGateway(AgentRuntime())
    assert gateway.submit_text('Какая сейчас громкость?', metadata={'session_id': 'volume-followup'}) == 'Громкость 94%.'
    assert gateway.submit_text('сделай 100', metadata={'session_id': 'volume-followup'}) == 'Громкость 100%.'
    assert actions == [('get_volume', {}), ('set_volume', {'level': 100})]


def test_active_task_does_not_pin_an_unbounded_tool_catalog(isolated_project):
    loop = isolated_project('agent_loop')
    session = loop.get_session('active-budget')
    session.begin_task('Открыть приложение и найти нужный элемент')
    session.task['discovered_tools'] = [s['function']['name'] for s in loop.ALL_TOOLS[:30]]
    tools = loop._tools_for_reasoning(session, 'продолжай', True)
    assert len(tools) <= 12
    assert {'observe', 'plan_task', 'verify_goal'} <= {s['function']['name'] for s in tools}
