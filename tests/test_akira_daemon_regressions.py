import pytest

from akira_daemon import AkiraDaemon


class Runtime:
    def heartbeat_tick(self):
        return []


def test_daemon_rejects_non_positive_heartbeat_interval():
    with pytest.raises(ValueError):
        AkiraDaemon(runtime=Runtime(), heartbeat_interval=0)


def test_daemon_rejects_negative_stop_timeout():
    daemon = AkiraDaemon(runtime=Runtime())
    with pytest.raises(ValueError):
        daemon.stop(timeout=-1)
