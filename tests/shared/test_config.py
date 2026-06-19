"""Test configuration settings."""
import pytest


def test_aether_llm_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("AETHER_LLM_ENABLED", raising=False)
    from shared.config import Settings
    s = Settings()
    assert s.aether_llm_enabled is False


def test_aether_llm_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("AETHER_LLM_ENABLED", "true")
    from shared.config import Settings
    s = Settings()
    assert s.aether_llm_enabled is True
