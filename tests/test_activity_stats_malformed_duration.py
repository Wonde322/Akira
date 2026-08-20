import activity_stats


def test_activity_stats_skips_malformed_duration_and_keeps_valid_session(monkeypatch):
    monkeypatch.setattr(
        activity_stats,
        "get_activity_for_period",
        lambda days: [
            {"app": "Broken", "duration_seconds": "not-a-number"},
            {"app": "Chrome", "duration_seconds": 125},
        ],
    )

    result = activity_stats.get_activity_stats(1)

    assert "Chrome" in result
    assert "2 мин" in result
    assert "Broken" not in result


def test_activity_stats_skips_negative_duration(monkeypatch):
    monkeypatch.setattr(
        activity_stats,
        "get_activity_for_period",
        lambda days: [
            {"app": "ClockSkew", "duration_seconds": -60},
            {"app": "Safari", "duration_seconds": 60},
        ],
    )

    result = activity_stats.get_activity_stats(1)

    assert "Safari" in result
    assert "ClockSkew" not in result
