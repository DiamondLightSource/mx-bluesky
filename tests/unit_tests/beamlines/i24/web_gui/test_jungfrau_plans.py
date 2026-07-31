from unittest.mock import MagicMock, patch

import pytest
from bluesky import RunEngine
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.beamlines.i24.aperture import Aperture
from dodal.devices.beamlines.i24.beamstop import Beamstop
from dodal.devices.beamlines.i24.commissioning_jungfrau import (
    CommissioningJungfrauDetector,
)
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.dual_backlight import DualBacklight
from dodal.devices.beamlines.i24.vgonio import VerticalGoniometer
from dodal.devices.hutch_shutter import InterlockedHutchShutter
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import MXZebraShutter

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.web_gui_plans.jungfrau_plans import (
    gui_run_jf_rotation_scan,
)


@pytest.fixture
def vertical_gonio() -> VerticalGoniometer:
    return i24.vgonio.build(connect_immediately=True, mock=True)


def test_run_jf_rotation(
    jungfrau: CommissioningJungfrauDetector,
    zebra: Zebra,
    enum_attenuator: EnumFilterAttenuator,
    aperture: Aperture,
    vertical_gonio: VerticalGoniometer,
    beamstop: Beamstop,
    detector_stage: YZStage,
    backlight: DualBacklight,
    dcm: DCM,
    synchrotron: Synchrotron,
    shutter: InterlockedHutchShutter,
    sample_shutter: MXZebraShutter,
    run_engine: RunEngine,
):
    composite = RotationScanComposite(
        aperture=aperture,
        attenuator=enum_attenuator,
        jungfrau=jungfrau,
        vgonio=vertical_gonio,
        synchrotron=synchrotron,
        sample_shutter=sample_shutter,
        zebra=zebra,
        shutter=shutter,
        beamstop=beamstop,
        detector_motion=detector_stage,
        backlight=backlight,
        dcm=dcm,
    )
    with patch(
        "mx_bluesky.beamlines.i24.web_gui_plans.jungfrau_plans.rotation_scan_plan",
        MagicMock(return_value=iter([])),
    ) as patch_inner_plan:
        run_engine(
            gui_run_jf_rotation_scan(
                "new_rotation", 0.01, 0.0, 0.1, 90, 300, 1, [0.3], composite
            )
        )

        patch_inner_plan.assert_called_once()
        # Keyword by keyword, because the GUI sends these positionally and a pair
        # transposed here would collect the wrong thing without failing.
        params = patch_inner_plan.call_args.args[1]
        assert params.filename == "new_rotation"
        assert params.exposure_time_s == 0.01
        assert params.omega_start_deg == 0.0
        assert params.rotation_increment_per_image_deg == 0.1
        assert params.scan_width_deg == 90
        assert params.detector_distance_mm == 300
        assert params.sample_id == 1
        assert params.transmission_fractions == [0.3]
