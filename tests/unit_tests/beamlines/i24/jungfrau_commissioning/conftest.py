import pytest
from dodal.beamlines.i24 import VerticalGoniometer
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.hutch_shutter import HutchShutter
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.testing import patch_all_motors
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import (
    RotationScanComposite,
)


@pytest.fixture
def rotation_composite(
    jungfrau: CommissioningJungfrau, zebra: Zebra, enum_attenuator: EnumFilterAttenuator
) -> RotationScanComposite:
    with init_devices(mock=True):
        aperture = Aperture("")
        gonio = VerticalGoniometer("")
        synchrotron = Synchrotron("")
        sample_shutter = ZebraShutter("")
        xbpm_feedback = XBPMFeedback("")
        hutch_shutter = HutchShutter("")
        beamstop = Beamstop("")
        det_stage = YZStage("")
        backlight = DualBacklight("")
        dcm = DCM("", "")

    patch_all_motors(det_stage)
    patch_all_motors(sample_shutter)
    patch_all_motors(gonio)
    patch_all_motors(dcm)

    composite = RotationScanComposite(
        aperture,
        enum_attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        xbpm_feedback,
        hutch_shutter,
        beamstop,
        det_stage,
        backlight,
        dcm,
    )

    return composite
