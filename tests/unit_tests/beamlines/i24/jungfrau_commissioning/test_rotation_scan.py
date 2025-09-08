import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines.i24 import VerticalGoniometer
from dodal.beamlines.i24 import attenuator as i24_attenuator
from dodal.devices.hutch_shutter import HutchShutter, ShutterState
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.util.test_utils import patch_all_motors
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from ophyd_async.core import init_devices
from ophyd_async.fastcs.jungfrau import Jungfrau
from ophyd_async.testing import set_mock_value
from tests.conftest import raw_params_from_file

from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import (
    RotationScanComposite,
    single_rotation_plan,
)
from mx_bluesky.common.parameters.rotation import SingleRotationScan


def get_good_rotation_params(tmp_path):
    params = raw_params_from_file(
        "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/test_good_rotation_params.json",
        tmp_path,
    )

    return SingleRotationScan(**params)


@pytest.fixture
def rotation_composite(jungfrau: Jungfrau, zebra: Zebra) -> RotationScanComposite:
    with init_devices(mock=True):
        aperture = Aperture("")
        attenuator = i24_attenuator()
        gonio = VerticalGoniometer("")
        synchrotron = Synchrotron("")
        sample_shutter = ZebraShutter("")
        hutch_shutter = HutchShutter("")
        beamstop = Beamstop("")
        det_stage = YZStage("")  # TODO add JF position to det stage device
        backlight = DualBacklight("")
        dcm = DCM("")

    patch_all_motors(det_stage)
    patch_all_motors(sample_shutter)
    patch_all_motors(gonio)

    composite = RotationScanComposite(
        aperture,
        attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        hutch_shutter,
        beamstop,
        det_stage,
        backlight,
        dcm,
    )

    return composite


def test_single_rotation_plan_in_re(
    RE: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    params = get_good_rotation_params(tmp_path)
    set_mock_value(
        rotation_composite.jungfrau._writer._drv.num_captured, params.num_images
    )
    set_mock_value(rotation_composite.hutch_shutter.status, ShutterState.OPEN)
    RE(single_rotation_plan(rotation_composite, params))


def test_metadata_writer_produces_correct_json_after_plan(): ...


def test_set_up_beamline_for_rotation(): ...


def test_single_rotation_plan_error_if_no_det_distance(): ...
