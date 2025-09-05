import bluesky.plan_stubs as bps
import pydantic
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import CryoStream
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.fluorescence_detector_motion import (
    FluorescenceDetector,
)
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.scintillator import InOut as ScinInOut
from dodal.devices.scintillator import Scintillator


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class UDCDefaultDevices:
    cryostream: CryoStream
    fluorescence_det_motion: FluorescenceDetector
    beamstop: Beamstop
    scintillator: Scintillator
    aperture_scatterguard: ApertureScatterguard
    collimation_table: CollimationTable


def move_to_udc_default_state(devices: UDCDefaultDevices):
    """Moves beamline to known positions prior to UDC start"""

    cryostream_temp = yield from bps.rd(devices.cryostream.temperature_k)
    cryostream_pressure = yield from bps.rd(devices.cryostream.back_pressure_bar)
    if cryostream_temp > devices.cryostream.MAX_TEMP_K:
        raise ValueError("Cryostream temperature is too high, not starting UDC")
    if cryostream_pressure > devices.cryostream.MAX_PRESSURE_BAR:
        raise ValueError("Cryostream back pressure is too high, not starting UDC")

    yield from bps.abs_set(devices.scintillator.selected_pos, ScinInOut.OUT, wait=True)

    yield from bps.abs_set(
        devices.fluorescence_det_motion.pos, FlouInOut.OUT, group="udc_default"
    )

    yield from bps.abs_set(devices.collimation_table.inboard_y, 0, group="udc_default")
    yield from bps.abs_set(devices.collimation_table.outboard_y, 0, group="udc_default")
    yield from bps.abs_set(devices.collimation_table.upstream_y, 0, group="udc_default")
    yield from bps.abs_set(devices.collimation_table.upstream_x, 0, group="udc_default")
    yield from bps.abs_set(
        devices.collimation_table.downstream_x, 0, group="udc_default"
    )

    yield from bps.abs_set(
        devices.beamstop.selected_pos,
        BeamstopPositions.DATA_COLLECTION,
        group="udc_default",
    )

    yield from bps.abs_set(
        devices.aperture_scatterguard.selected_aperture,
        ApertureValue.SMALL,
        group="udc_default",
    )

    yield from bps.abs_set(devices.cryostream.course, CryoInOut.IN, group="udc_default")
    yield from bps.abs_set(devices.cryostream.fine, CryoInOut.IN, group="udc_default")

    yield from bps.wait("udc_default")
