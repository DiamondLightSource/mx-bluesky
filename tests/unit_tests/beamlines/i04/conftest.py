from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.backlight import Backlight
from dodal.devices.beamsize.beamsize import BeamsizeBase
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import ZebraFastGridScanThreeD
from dodal.devices.flux import Flux
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback
from mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan import (
    I04GridDetectThenXRayCentreComposite,
)


@pytest.fixture
def murko_callback() -> MurkoCallback:
    callback = MurkoCallback("", "")
    callback.redis_client = MagicMock()
    callback.redis_connected = True
    return callback


@pytest.fixture(autouse=True)
def always_use_i04_beamline(monkeypatch, patch_beamline_env_variable):
    monkeypatch.setenv("BEAMLINE", "i04")


@pytest.fixture(autouse=True)
def patch_get_i04_feature_settings():
    fake_path = "tests/test_data/test_domain_properties"
    with patch(
        "mx_bluesky.beamlines.i04.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
        str(fake_path),
    ):
        yield


@pytest.fixture
async def grid_detect_xrc_devices(
    aperture_scatterguard: ApertureScatterguard,
    backlight: Backlight,
    beamstop_phase1: Beamstop,
    beamsize: BeamsizeBase,
    detector_motion: DetectorMotion,
    eiger: EigerDetector,
    smargon: Smargon,
    oav: OAV,
    ophyd_pin_tip_detection: PinTipDetection,
    zocalo: ZocaloResults,
    synchrotron: Synchrotron,
    fast_grid_scan: ZebraFastGridScanThreeD,
    s4_slit_gaps: S4SlitGaps,
    flux: Flux,
    zebra,
    zebra_shutter,
    xbpm_feedback,
    attenuator,
    undulator,
    dcm,
):
    yield I04GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_phase1,
        beamsize=beamsize,
        detector_motion=detector_motion,
        eiger=eiger,
        zebra_fast_grid_scan=fast_grid_scan,
        flux=flux,
        oav=oav,
        pin_tip_detection=ophyd_pin_tip_detection,
        gonio=smargon,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        undulator=undulator,
        xbpm_feedback=xbpm_feedback,
        zebra=zebra,
        zocalo=zocalo,
        dcm=dcm,
        robot=MagicMock(spec=BartRobot),
        sample_shutter=zebra_shutter,
    )
