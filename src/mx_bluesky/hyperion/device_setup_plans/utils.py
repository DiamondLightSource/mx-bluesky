from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.detector import (
    DetectorParams,
)


def fill_in_energy_if_not_supplied(
    dcm: DoubleCrystalMonochromator, detector_params: DetectorParams
) -> MsgGenerator[DetectorParams]:
    if not detector_params.expected_energy_ev:
        actual_energy_ev = 1000 * (yield from bps.rd(dcm.energy_in_keV))
        detector_params.expected_energy_ev = actual_energy_ev
    return detector_params
