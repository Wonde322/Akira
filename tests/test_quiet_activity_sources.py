from types import SimpleNamespace


def test_ambient_patterns_remain_silent_with_or_without_inferred_task():
    from proactive_runtime import ProactiveRuntime, ProactiveAction
    runtime = ProactiveRuntime(dedupe_seconds=0)
    for kind in ('desktop.context.repeated', 'desktop.context.dwell'):
        result = runtime.decide({'type': kind, 'payload': {'message': 'Ты вернулся', 'count': 5, 'seconds': 3600, 'active_task': {'goal': 'Дизайн', 'confidence': 0.99}}})
        assert result.action == ProactiveAction.RECORD


def test_tracker_minute_flushes_share_visit_id_and_switches_get_new_id(monkeypatch):
    import activity_tracker
    rows = []
    monkeypatch.setattr(activity_tracker, 'save_session', lambda *args, **kwargs: rows.append((args, kwargs)))
    tracker = activity_tracker.ActivityTracker()
    tracker.sample('Chrome', '2026-10-28T10:00:00+04:00', context='Курс')
    tracker.sample('Chrome', '2026-10-28T10:01:00+04:00', context='Курс')
    tracker.sample('Chrome', '2026-10-28T10:02:00+04:00', context='Курс')
    tracker.sample('Figma', '2026-10-28T10:02:10+04:00', context='Сайт')
    tracker.flush('2026-10-28T10:03:00+04:00')
    assert rows[0][1]['visit_id'] == rows[1][1]['visit_id']
    assert rows[-1][1]['visit_id'] != rows[0][1]['visit_id']
    assert rows[0][1]['context'] == 'Курс'


def test_source_buttons_open_only_extracted_web_urls(qapp, monkeypatch):
    from desktop_app.text_window import TextChatView
    from PySide6.QtWidgets import QToolButton
    monkeypatch.setattr('desktop_app.text_window.QDesktopServices.openUrl', lambda url: opened.append(url.toString()))
    opened = []
    chat = TextChatView()
    chat.add_message('Ответ [Источник](https://example.com/page). https://other.org/a', 'akira')
    buttons = chat.findChildren(QToolButton)
    assert len(buttons) == 2
    buttons[0].click()
    assert opened == ['https://example.com/page']
    assert not buttons[0].icon().isNull()
    chat.deleteLater()


def test_near_deadline_linked_goal_can_offer_help():
    from proactive_runtime import ProactiveRuntime, ProactiveAction
    runtime = ProactiveRuntime(dedupe_seconds=0, orchestrator=SimpleNamespace(decide=lambda *args: {'spawn': False}))
    result = runtime.decide({'type': 'desktop.context.repeated', 'payload': {
        'count': 3, 'active_task': {'goal': 'Макет', 'confidence': 0.9},
        'active_goal': {'title': 'Макет', 'deadline': '2026-10-28T20:00:00+04:00', 'urgency': 0.95, 'confidence': 0.9}}})
    assert result.action == ProactiveAction.ASK_USER
    assert '2026-10-28' in result.notification


def test_activity_timezone_and_metadata_remain_readable(isolated_project):
    from datetime import datetime, timedelta
    memory = isolated_project('memory')
    now = datetime.now().astimezone()
    memory.add_activity_session('Chrome', (now - timedelta(minutes=2)).isoformat(), now.isoformat(), 120,
                                context='Курс', visit_id='one-visit')
    rows = memory.get_activity_for_period(1)
    assert rows[-1]['context'] == 'Курс'
    assert rows[-1]['visit_id'] == 'one-visit'
