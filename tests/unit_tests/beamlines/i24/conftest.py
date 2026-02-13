import pytest


@pytest.fixture(autouse=True)
def patch_beamline_env_variable(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i24")
