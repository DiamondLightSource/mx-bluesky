import pytest


@pytest.fixture()
def use_i24_beamline(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i24")
