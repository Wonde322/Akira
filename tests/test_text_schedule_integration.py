from datetime import timedelta
from types import SimpleNamespace
import time


def test_scheduled_goal_runs_and_delivers_result_to_text_window(tmp_path, monkeypatch, qapp):
    import agent_runtime, event_bus, proactive_runtime, scheduler, task_runtime
    from agent_runtime import AgentRuntime
    from proactive_inbox import ProactiveInbox
    from proactive_delivery import ProactiveDelivery
    from desktop_app.proactive_surface import ProactiveDesktopBridge
    from desktop_app.text_window import TextMainWindow
    from desktop_app.worker import BrainWorker
    from PySide6.QtWidgets import QLabel

    monkeypatch.setattr(event_bus, 'RUNTIME_DIR', tmp_path)
    monkeypatch.setattr(event_bus, 'TRIGGER_FILE', tmp_path / 'triggers.json')
    monkeypatch.setattr(event_bus, 'EVENT_LOG', tmp_path / 'events.jsonl')
    monkeypatch.setattr(scheduler, 'RUNTIME_DIR', tmp_path)
    monkeypatch.setattr(scheduler, 'SCHEDULE_FILE', tmp_path / 'schedule.json')
    monkeypatch.setattr(task_runtime, 'TASK_FILE', tmp_path / 'background.json')
    monkeypatch.setattr(agent_runtime, 'get_agent_runtime', lambda: AgentRuntime(executor=lambda *a, **k: 'Результат готов'))
    tasks = task_runtime.TaskRuntime(max_workers=1)
    monkeypatch.setattr(task_runtime, 'get_runtime', lambda: tasks)
    inbox = ProactiveInbox(path=tmp_path / 'inbox.json')
    proactive = proactive_runtime.ProactiveRuntime(inbox=inbox, attention_budget=SimpleNamespace(allow=lambda *a: True))
    bus = event_bus.EventBus()
    monkeypatch.setattr(event_bus, 'get_event_bus', lambda: bus)
    monkeypatch.setattr(proactive_runtime, 'get_proactive_runtime', lambda: proactive)
    bridge = ProactiveDesktopBridge(delivery=ProactiveDelivery(inbox=inbox))
    services = SimpleNamespace(start=lambda: None, request_stop=lambda: None, is_running=lambda: False)
    monkeypatch.setattr(BrainWorker, 'start', lambda self: None)
    window = TextMainWindow(services=services, proactive=bridge)
    instance = scheduler.Scheduler()
    instance.create('Проверить задачу', scheduler._iso(scheduler._now() - timedelta(seconds=1)))
    try:
        dispatched = instance.tick()
        assert dispatched['launched']
        deadline = time.monotonic() + 2
        while not inbox.list() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(.005)
        bridge.poll()
        qapp.processEvents()
        assert any('Результат готов' in label.text() for label in window.chat.findChildren(QLabel))
    finally:
        tasks.shutdown(wait=True)
        window.close()
        qapp.processEvents()
