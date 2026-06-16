from shared.config import Settings


def test_smart_flags_default_off():
    s = Settings()
    assert s.self_healing_enabled is False
    assert s.cost_router_v2_enabled is False
    assert s.monitor_enabled is False
    assert s.monitor_interval_seconds == 30


def test_smart_flags_env_override(monkeypatch):
    monkeypatch.setenv("SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_INTERVAL_SECONDS", "15")
    s = Settings()
    assert s.self_healing_enabled is True
    assert s.monitor_interval_seconds == 15
