import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from dodal.devices.zebra import Zebra
from ophyd.status import Status


@pytest.fixture
def done_status():
    status = Status()
    status.set_finished()
    return status


@pytest.fixture
def zebra() -> Zebra:
    RunEngine()
    zebra = i24.zebra(fake_with_ophyd_sim=True)
    return zebra


@pytest.fixture
def RE():
    return RunEngine()
