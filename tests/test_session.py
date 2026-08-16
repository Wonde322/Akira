from session import Session


def test_session_isolates_history_between_instances():
    first = Session(session_id="one")
    second = Session(session_id="two")

    first.add({"role": "user", "content": "привет"})
    second.add({"role": "user", "content": "пока"})

    assert first.history == [{"role": "user", "content": "привет"}]
    assert second.history == [{"role": "user", "content": "пока"}]
    assert first.session_id != second.session_id


def test_session_trim_keeps_only_last_max_history_messages():
    session = Session(session_id="s", max_history=3)

    for index in range(6):
        session.add({"role": "user", "content": str(index)})

    session.trim()

    assert len(session.history) == 3
    assert session.history[0]["content"] == "3"


def test_session_trim_keeps_intact_pairs_and_leading_user():
    session = Session(session_id="s", max_history=6)

    session.add({"role": "user", "content": "u1"})
    session.add({"role": "assistant", "content": "a1", "tool_calls": []})
    session.add({"role": "tool", "tool_call_id": "t1", "content": "r1"})
    session.add({"role": "user", "content": "u2"})
    session.add({"role": "assistant", "content": "a2", "tool_calls": []})
    session.add({"role": "tool", "tool_call_id": "t2", "content": "r2"})
    session.add({"role": "assistant", "content": "answer"})

    session.trim()

    assert session.history == [
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2", "tool_calls": []},
        {"role": "tool", "tool_call_id": "t2", "content": "r2"},
        {"role": "assistant", "content": "answer"},
    ]


def test_session_trim_preserves_latest_user_and_pairs():
    session = Session(session_id="s", max_history=5)

    session.add({"role": "user", "content": "old"})
    session.add({"role": "assistant", "content": "a_old", "tool_calls": []})
    session.add({"role": "tool", "tool_call_id": "t_old", "content": "r"})
    session.add({"role": "user", "content": "new"})
    session.add({"role": "assistant", "content": "a_new", "tool_calls": []})
    session.add({"role": "tool", "tool_call_id": "t_new", "content": "r"})
    session.add({"role": "assistant", "content": "answer"})

    session.trim()

    roles = [message["role"] for message in session.history]

    assert roles == ["user", "assistant", "tool", "assistant"]
    assert session.history[0]["content"] == "new"


def test_session_trim_without_user_in_window_becomes_empty():
    session = Session(session_id="s", max_history=3)

    for index in range(3):
        session.add({"role": "assistant", "content": f"a{index}"})
        session.add({"role": "tool", "tool_call_id": f"t{index}", "content": "res"})

    session.trim()

    assert session.history == []


def test_session_trim_without_history_is_noop():
    session = Session(session_id="s", max_history=4)

    session.trim()

    assert session.history == []


def test_session_default_id_is_unique():
    assert Session().session_id != Session().session_id


def test_brain_get_session_isolates_by_id(isolated_project):
    brain = isolated_project("brain")

    first = brain.get_session("alpha")
    second = brain.get_session("beta")

    assert first.session_id == "alpha"
    assert second.session_id == "beta"

    first.add({"role": "user", "content": "только мне"})

    assert second.history == []

    assert brain.get_session("alpha") is first


def test_brain_default_session_is_shared_conversation_alias(isolated_project):
    brain = isolated_project("brain")

    session = brain.get_session(None)

    assert brain.conversation is session.history