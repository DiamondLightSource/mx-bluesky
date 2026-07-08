import pytest


@pytest.fixture(autouse=True)
def always_use_i03_beamline(use_beamline_i03): ...
