import time

from test_text_desktop_lifecycle import window, wait_until


def test_chat_store_survives_restart_with_separate_histories(tmp_path):
    from desktop_app.chat_store import ChatStore
    path = tmp_path / 'chats.json'
    store = ChatStore(path)
    first = store.active
    store.append('Первый проект', 'user')
    second = store.create()['id']
    store.append('Другой проект', 'user')
    restored = ChatStore(path)
    assert restored.active == second
    assert restored.get(first)['messages'] == [{'text': 'Первый проект', 'role': 'user'}]
    assert restored.get(second)['title'] == 'Другой проект'
    assert path.stat().st_mode & 0o077 == 0


def test_switch_during_reply_routes_answer_to_original_chat(window):
    first = window.chat_store.active
    window._chat_busy(first, True)
    window._create_chat()
    second = window.chat_store.active
    assert not window.chat.typing.timer.isActive()
    window._chat_answer(first, 'Ответ в первом чате')
    assert not any(m['text'] == 'Ответ в первом чате' for m in window.chat_store.get(second)['messages'])
    window.chat_selector.setCurrentIndex(window.chat_selector.findData(first))
    assert window.chat.typing.timer.isActive()
    assert window.chat_store.get()['messages'][-1]['text'] == 'Ответ в первом чате'
    window._chat_busy(first, False)
    assert not window.chat.typing.timer.isActive()


def test_scroll_reaches_bottom_after_wrapped_answer_layout(window, qapp):
    window.show()
    for index in range(20):
        window.chat.add_message(('Длинный ответ ' * 25) + str(index), 'akira')
    wait_until(qapp, lambda: window.chat.verticalScrollBar().maximum() > 0)
    for _ in range(8):
        qapp.processEvents()
    bar = window.chat.verticalScrollBar()
    assert bar.value() == bar.maximum()
    window.chat.add_message('Последняя строка\n' * 20, 'akira')
    for _ in range(8):
        qapp.processEvents()
    assert bar.value() == bar.maximum()


def test_worker_captures_chat_when_queued(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    calls = []
    class Gateway:
        def submit_text(self, message, **kwargs):
            calls.append(kwargs['metadata']['session_id'])
            return message
    worker._gateway = Gateway()
    answers = []
    worker.chat_answer.connect(lambda chat, text: answers.append((chat, text)))
    worker.submit('Первый', session_id='one')
    worker.submit('Второй', session_id='two')
    worker.session_id = 'unrelated'
    worker.start()
    try:
        wait_until(qapp, lambda: len(answers) == 2)
        assert calls == ['one', 'two']
        assert answers == [('one', 'Первый'), ('two', 'Второй')]
    finally:
        worker.request_stop()
        assert worker.wait(1000)


def test_worker_restores_recent_transcript_without_overwriting_live_session(qapp, monkeypatch):
    import sys
    from types import SimpleNamespace
    from session import Session
    from desktop_app.worker import BrainWorker
    session = Session('restored')
    monkeypatch.setitem(sys.modules, 'agent_loop', SimpleNamespace(get_session=lambda key: session))
    seen = []
    class Gateway:
        def submit_text(self, message, **kwargs):
            seen.append(list(session.history))
            session.add({'role': 'user', 'content': message})
            return 'ok'
    worker = BrainWorker()
    worker._gateway = Gateway()
    answers = []
    worker.chat_answer.connect(lambda *args: answers.append(args))
    transcript = [{'role': 'user', 'text': 'Меня зовут Миша'}, {'role': 'akira', 'text': 'Запомнил.'}]
    worker.submit('Как меня зовут?', session_id='restored', history=transcript)
    worker.submit('Продолжим', session_id='restored', history=transcript)
    worker.start()
    try:
        wait_until(qapp, lambda: len(answers) == 2)
        assert seen[0] == [{'role': 'user', 'content': 'Меня зовут Миша'}, {'role': 'assistant', 'content': 'Запомнил.'}]
        assert seen[1][-1]['content'] == 'Как меня зовут?'
    finally:
        worker.request_stop()
        assert worker.wait(1000)


def test_sidebar_history_and_new_chat_accept_full_row_clicks(window, qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    window.show()
    qapp.processEvents()
    assert window.sidebar.isVisible()
    count = len(window.chat_store.chats)
    QTest.mouseClick(window.new_chat, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert len(window.chat_store.chats) == count + 1
    assert window.history.count() == count + 1
    row = window.history.visualItemRect(window.history.item(0))
    QTest.mouseClick(window.history.viewport(), Qt.MouseButton.LeftButton,
                    pos=QPoint(row.right()-4, row.center().y()))
    assert window.chat_store.active == window.chat_selector.itemData(0)
    window.resize(660, 680)
    qapp.processEvents()
    assert not window.sidebar.isVisible()
    assert window.input.isVisible() and window.send.isVisible()


def test_chat_popup_has_explicit_geometry_rows_and_selection(window, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window._create_chat()
    window.show()
    qapp.processEvents()
    selector = window.chat_selector
    selector.showPopup()
    qapp.processEvents()
    assert selector.popup.width() == selector.width()
    assert selector.popup.y() == selector.mapToGlobal(selector.rect().bottomLeft()).y() + 9
    assert selector.popup_list.item(0).sizeHint().height() == 44
    target = selector.popup_list.visualItemRect(selector.popup_list.item(0)).center()
    QTest.mouseClick(selector.popup_list.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert selector.currentIndex() == 0
    assert not selector.popup.isVisible()
    selector.showPopup()
    QTest.keyClick(selector.popup_list, Qt.Key.Key_Escape)
    assert not selector.popup.isVisible()


def test_single_action_switches_between_send_and_cancel(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, '_cancel_current', lambda: calls.append('stop'))
    window._on_busy(True)
    assert window.send.text() == '■'
    window.send.click()
    assert calls == ['stop']
    window._on_busy(False)
    assert window.send.text() == '↑'
    assert window.send.isEnabled()


def test_delete_chat_discards_queued_work_and_late_replies(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    deleted = window.chat_store.active
    window.worker.submit('Не выполнять', session_id=deleted)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window._delete_chat()
    assert deleted not in [c['id'] for c in window.chat_store.chats]
    assert window.worker._queue.empty()
    window._chat_answer(deleted, 'Поздний ответ')
    assert not window.chat_store.get()['messages']


def test_file_picker_adds_paths_to_request_and_persisted_context(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    path = tmp_path / 'notes.txt'
    path.write_text('Текст файла', encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *args: ([str(path)], ''))
    window.attach.click()
    assert path.name in window.attachment_label.text()
    window.input.setPlainText('Прочитай файл')
    window.submit_current()
    message = window.worker._queue.get_nowait()[0]
    assert str(path) in message
    assert str(path) in window.chat_store.get()['messages'][-1]['context']
    assert not window._attachments


def test_chat_titles_display_with_initial_capital(window):
    window.chat_store.get()['title'] = 'привет NASA'
    window._refresh_chats()
    assert window.chat_selector.currentText() == 'Привет NASA'
    assert window.attach.text() == ''
