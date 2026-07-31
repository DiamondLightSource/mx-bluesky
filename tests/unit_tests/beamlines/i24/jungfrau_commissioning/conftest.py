import pytest
from dodal.beamlines import i24
from dodal.beamlines.i24 import VerticalGoniometer
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.beamlines.i24.aperture import Aperture
from dodal.devices.beamlines.i24.beamstop import Beamstop
from dodal.devices.beamlines.i24.commissioning_jungfrau import (
    CommissioningJungfrauDetector,
)
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.dual_backlight import DualBacklight
from dodal.devices.hutch_shutter import InterlockedHutchShutter
from dodal.devices.interlocks import PSSInterlock
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import MXZebraShutter
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.i24.jungfrau_commissioning.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)


@pytest.fixture
def zebra() -> Zebra:
    """Override the shared fixture, which builds i03's zebra.

    These are i24 plans, and the two beamlines wire their zebra outputs differently:
    i24 maps TTL_JUNGFRAU where i03 maps TTL_DETECTOR. Testing against i03's mapping
    hides exactly the mismatch that UnmappedZebraError exists to catch.
    """
    return i24.zebra.build(connect_immediately=True, mock=True)


@pytest.fixture
def rotation_composite(
    jungfrau: CommissioningJungfrauDetector,
    zebra: Zebra,
    enum_attenuator: EnumFilterAttenuator,
) -> RotationScanComposite:
    with init_devices(mock=True):
        aperture = Aperture("")
        vgonio = VerticalGoniometer("")
        synchrotron = Synchrotron("")
        sample_shutter = MXZebraShutter("")
        shutter = InterlockedHutchShutter("", PSSInterlock(""))
        beamstop = Beamstop("")
        detector_motion = YZStage("")
        backlight = DualBacklight("")
        dcm = DCM("", "")

    # By keyword: the field names must match the i24 dodal device names, since that is
    # how blueapi resolves them, so a rename here is a real change rather than a shuffle.
    composite = RotationScanComposite(
        aperture=aperture,
        attenuator=enum_attenuator,
        jungfrau=jungfrau,
        vgonio=vgonio,
        synchrotron=synchrotron,
        sample_shutter=sample_shutter,
        zebra=zebra,
        shutter=shutter,
        beamstop=beamstop,
        detector_motion=detector_motion,
        backlight=backlight,
        dcm=dcm,
    )

    return composite


@pytest.fixture(autouse=True)
def always_use_i24_beamline(use_i24_beamline): ...
