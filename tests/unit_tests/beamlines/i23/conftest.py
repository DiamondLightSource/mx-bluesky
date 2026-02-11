import pytest


@pytest.fixture()
def patch_beamline_env_variable(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i23")
