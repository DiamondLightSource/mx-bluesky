import pytest


@pytest.fixture(autouse=True)
def always_patch_beamline_env_variable(patch_beamline_env_variable): ...
