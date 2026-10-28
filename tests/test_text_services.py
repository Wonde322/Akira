from types import SimpleNamespace
from threading import Event
import time

import pytest


def test_heartbeat_runs_independent_sources_without_model_calls():
    from desktop_app.services import DesktopServices
    calls = []
    services = DesktopServices(
        scheduler=SimpleNamespace(tick=lambda: calls.append('schedule')),
        awareness=SimpleNamespace(sample=lambda **kw: calls.append(('awareness', kw))),
        tracker=SimpleNamespace(sample=lambda: calls.append('activity'), flush=lambda: None),
    )
    services.heartbeat.tick()
    assert calls == ['schedule', ('awareness', {'capture': False}), 'activity']


def test_failing_service_does_not_stop_other_sources():
    from desktop_app.services import DesktopServices
    calls = []
    def fail():
        raise RuntimeError('unavailable')
    services = DesktopServices(
        scheduler=SimpleNamespace(tick=fail),
        awareness=SimpleNamespace(sample=lambda **kw: calls.append('awareness')),
        tracker=SimpleNamespace(sample=lambda: calls.append('activity'), flush=lambda: None),
    )
    services.heartbeat.tick()
    assert calls == ['awareness', 'activity']
    assert services.heartbeat.last_results['scheduler']['type'] == 'heartbeat.error'


def test_service_shutdown_cancels_background_work_and_stops_polling():
    from desktop_app.services import DesktopServices
    entered = Event()
    stopped = []
    services = DesktopServices(
        interval=.01, scheduler=SimpleNamespace(tick=lambda: entered.set()),
        awareness=SimpleNamespace(sample=lambda **kw: None),
        tasks=SimpleNamespace(shutdown=lambda **kw: stopped.append(kw), has_active=lambda: False),
        tracker=SimpleNamespace(sample=lambda: None, flush=lambda: None),
    )
    services.start()
    assert entered.wait(1)
    services.request_stop()
    services._daemon.stop(timeout=1)
    assert not services.is_running()
    assert stopped == [{'wait': False}]
    assert services._schedule() is None


def test_activity_sampler_records_switches_and_long_sessions(monkeypatch):
    import activity_tracker
    calls = []
    monkeypatch.setattr(activity_tracker, 'save_session', lambda *args, **kwargs: calls.append(args))
    tracker = activity_tracker.ActivityTracker()
    tracker.sample('Figma', '2026-10-28T10:00:00+04:00')
    tracker.sample('Figma', '2026-10-28T10:01:00+04:00')
    tracker.sample('Chrome', '2026-10-28T10:01:30+04:00')
    assert calls == [('Figma', '2026-10-28T10:00:00+04:00', '2026-10-28T10:01:00+04:00'), ('Figma', '2026-10-28T10:01:00+04:00', '2026-10-28T10:01:30+04:00')]


def test_legacy_tool_failure_is_not_wrapped_as_success(isolated_project, monkeypatch):
    loop = isolated_project('agent_loop')
    failure = {'success': False, 'error': 'element_not_found', 'output': 'missing'}
    monkeypatch.setattr(loop, 'get_permission', lambda name: 'auto')
    monkeypatch.setattr(loop, 'get_tool_implementation', lambda name: lambda: failure)
    result, _ = loop._execute('browser_click', {})
    assert result is failure
    assert result['success'] is False


@pytest.mark.parametrize('result,status', [
    ({'success': False, 'error': 'cancelled', 'output': 'cancelled'}, 'cancelled'),
    ({'success': False, 'error': 'failed', 'output': 'network'}, 'failed'),
    ({'success': True, 'data': 'done', 'error': None}, 'completed'),
])
def test_background_structured_result_controls_terminal_status(tmp_path, monkeypatch, result, status):
    import task_runtime
    import agent_runtime
    monkeypatch.setattr(task_runtime, 'TASK_FILE', tmp_path / 'tasks.json')
    monkeypatch.setattr(agent_runtime, 'get_agent_runtime', lambda: SimpleNamespace(run=lambda *a, **k: result))
    runtime = task_runtime.TaskRuntime(max_workers=1)
    monkeypatch.setattr(runtime, '_emit', lambda *a: None)
    task = runtime._make_task('test')
    runtime._tasks[task['id']] = task
    runtime._run(task['id'])
    assert runtime.status(task['id'])['task']['status'] == status
    if status == 'completed':
        assert runtime.result(task['id'])['output'] == 'done'
    runtime.shutdown()


def test_shutdown_cancels_running_task_and_rejects_new_work(tmp_path, monkeypatch):
    import task_runtime
    import agent_runtime
    from agent_runtime import AgentRuntime
    from execution_context import raise_if_execution_cancelled
    entered = Event()
    def execute(*a, **k):
        entered.set()
        while True:
            raise_if_execution_cancelled()
            time.sleep(.005)
    agent = AgentRuntime(executor=execute)
    monkeypatch.setattr(agent_runtime, 'get_agent_runtime', lambda: agent)
    monkeypatch.setattr(task_runtime, 'TASK_FILE', tmp_path / 'tasks.json')
    runtime = task_runtime.TaskRuntime(max_workers=1)
    monkeypatch.setattr(runtime, '_emit', lambda *a: None)
    started = runtime.spawn('test')
    assert entered.wait(1)
    runtime.shutdown(wait=True)
    assert not runtime.has_active()
    assert runtime.status(started['task_id'])['task']['status'] == 'cancelled'
    assert runtime.spawn('another')['error'] == 'runtime_closed'
