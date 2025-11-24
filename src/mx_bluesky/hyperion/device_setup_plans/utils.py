from bluesky import plan_stubs as bps
from dodal.devices.detector import (
    DetectorParams,
)
from dodal.devices.i03.dcm import DCM


def fill_in_energy_if_not_supplied(dcm: DCM, detector_params: DetectorParams):
    if not detector_params.expected_energy_ev:
        actual_energy_ev = 1000 * (yield from bps.rd(dcm.energy_in_keV))
        detector_params.expected_energy_ev = actual_energy_ev
    return detector_params
