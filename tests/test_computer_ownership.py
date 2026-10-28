from threading import Event, Thread
import time

from agent_runtime import AgentRuntime
from computer_access import desktop_access


def test_desktop_ownership_lasts_until_turn_ends_but_other_reasoning_can_run():
    owner_acquired, release_owner, contender_started, contender_acquired, independent_done = [Event() for _ in range(5)]
    def first(*a, **k):
        with desktop_access('click'):
            owner_acquired.set()
        # Ownership must remain while reasoning between actions.
        assert release_owner.wait(2)
        return 'first'
    def second(*a, **k):
        contender_started.set()
        with desktop_access('type'):
            contender_acquired.set()
        return 'second'
    def independent(*a, **k):
        with desktop_access('read'):
            independent_done.set()
        return 'read'
    one = Thread(target=lambda: AgentRuntime(executor=first).run('one'))
    two = Thread(target=lambda: AgentRuntime(executor=second).run('two'))
    three = Thread(target=lambda: AgentRuntime(executor=independent).run('three'))
    one.start()
    try:
        assert owner_acquired.wait(1)
        two.start(); three.start()
        assert contender_started.wait(1)
        assert independent_done.wait(1)
        assert not contender_acquired.is_set()
        release_owner.set()
        assert contender_acquired.wait(1)
    finally:
        release_owner.set()
        one.join(2)
        if two.ident: two.join(2)
        if three.ident: three.join(2)
    assert not any(thread.is_alive() for thread in [one,two,three])


def test_cancel_while_waiting_for_desktop_never_executes_action():
    acquired, release, started = Event(), Event(), Event()
    results = []
    def owner(*a, **k):
        with desktop_access('click'):
            acquired.set()
            assert release.wait(2)
    def waiter(*a, **k):
        started.set()
        with desktop_access('click'):
            raise AssertionError('cancelled waiter executed')
    runtime = AgentRuntime(executor=waiter)
    first = Thread(target=lambda: AgentRuntime(executor=owner).run('owner'))
    second = Thread(target=lambda: results.append(runtime.run('waiter', task_id='waiting')))
    first.start()
    try:
        assert acquired.wait(1)
        second.start()
        assert started.wait(1)
        assert runtime.cancel('waiting')
        second.join(1)
        assert results[0]['error'] == 'cancelled'
    finally:
        release.set()
        first.join(2)
        if second.ident: second.join(2)
