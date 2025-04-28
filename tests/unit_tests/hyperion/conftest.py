from collections.abc import Generator
from functools import partial
from importlib import resources
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator
from dodal.beamlines import i03
from dodal.common.beamlines import beamline_utils
from dodal.common.beamlines.beamline_parameters import (
    GDABeamlineParameters,
)
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.i03.beamstop import Beamstop, BeamstopPositions
from dodal.devices.i03.dcm import DCM
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.util.test_utils import patch_motor
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from ophyd.sim import NullStatus
from ophyd_async.core import (
    AsyncStatus,
)
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan
from tests.conftest import (
    default_raw_gridscan_params,
    raw_params_from_file,
)

i03.DAQ_CONFIGURATION_PATH = "tests/test_data/test_daq_configuration"
BANNED_PATHS = [Path("/dls"), Path("/dls_sw")]


@pytest.fixture
def load_centre_collect_params():
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json"
    )
    return LoadCentreCollect(**json_dict)


@pytest.fixture(autouse=True)
def patch_open_to_prevent_dls_reads_in_tests():
    unpatched_open = open
    assert __package__
    project_folder = resources.files(__package__)
    assert isinstance(project_folder, Path)
    project_folder = project_folder.parent.parent.parent

    def patched_open(*args, **kwargs):
        requested_path = Path(args[0])
        if requested_path.is_absolute():
            for p in BANNED_PATHS:
                assert not requested_path.is_relative_to(p), (
                    f"Attempt to open {requested_path} from inside a unit test"
                )
        return unpatched_open(*args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        yield []


@pytest.fixture
async def fake_fgs_composite(
    smargon: Smargon,
    test_fgs_params: HyperionSpecifiedThreeDGridScan,
    RE: RunEngine,
    done_status,
    attenuator,
    xbpm_feedback,
    synchrotron,
    aperture_scatterguard,
    zocalo,
    dcm,
    panda,
    backlight,
):
    fake_composite = HyperionFlyScanXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        dcm=dcm,
        # We don't use the eiger fixture here because .unstage() is used in some tests
        eiger=i03.eiger(connect_immediately=True, mock=True),
        zebra_fast_grid_scan=i03.zebra_fast_grid_scan(
            connect_immediately=True, mock=True
        ),
        flux=i03.flux(connect_immediately=True, mock=True),
        s4_slit_gaps=i03.s4_slit_gaps(connect_immediately=True, mock=True),
        smargon=smargon,
        undulator=i03.undulator(connect_immediately=True, mock=True),
        synchrotron=synchrotron,
        xbpm_feedback=xbpm_feedback,
        zebra=i03.zebra(connect_immediately=True, mock=True),
        zocalo=zocalo,
        panda=panda,
        panda_fast_grid_scan=i03.panda_fast_grid_scan(
            connect_immediately=True, mock=True
        ),
        robot=i03.robot(connect_immediately=True, mock=True),
        sample_shutter=i03.sample_shutter(connect_immediately=True, mock=True),
    )

    fake_composite.eiger.stage = MagicMock(return_value=done_status)
    # unstage should be mocked on a per-test basis because several rely on unstage
    fake_composite.eiger.set_detector_parameters(test_fgs_params.detector_params)
    fake_composite.eiger.stop_odin_when_all_frames_collected = MagicMock()
    fake_composite.eiger.odin.check_and_wait_for_odin_state = lambda timeout: True

    test_result = {
        "centre_of_mass": [6, 6, 6],
        "max_voxel": [5, 5, 5],
        "max_count": 123456,
        "n_voxels": 321,
        "total_count": 999999,
        "bounding_box": [[3, 3, 3], [9, 9, 9]],
    }

    @AsyncStatus.wrap
    async def mock_complete(result):
        await fake_composite.zocalo._put_results([result], {"dcid": 0, "dcgid": 0})

    fake_composite.zocalo.trigger = MagicMock(
        side_effect=partial(mock_complete, test_result)
    )  # type: ignore
    fake_composite.zocalo.timeout_s = 3
    set_mock_value(fake_composite.zebra_fast_grid_scan.scan_invalid, False)
    set_mock_value(fake_composite.zebra_fast_grid_scan.position_counter, 0)
    set_mock_value(fake_composite.smargon.x.max_velocity, 10)

    set_mock_value(fake_composite.robot.barcode, "BARCODE")

    return fake_composite


@pytest.fixture
def test_rotation_params_nomove():
    return MultiRotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters_nomove.json"
        )
    )


@pytest.fixture
def test_multi_rotation_params():
    return MultiRotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_multi_rotation_scan_parameters.json"
        )
    )


@pytest.fixture
def beamstop_i03(
    beamline_parameters: GDABeamlineParameters, sim_run_engine: RunEngineSimulator
) -> Generator[Beamstop, Any, Any]:
    with patch(
        "dodal.beamlines.i03.get_beamline_parameters", return_value=beamline_parameters
    ):
        beamstop = i03.beamstop(connect_immediately=True, mock=True)
        patch_motor(beamstop.x_mm)
        patch_motor(beamstop.y_mm)
        patch_motor(beamstop.z_mm)
        set_mock_value(beamstop.x_mm.user_readback, 1.52)
        set_mock_value(beamstop.y_mm.user_readback, 44.78)
        set_mock_value(beamstop.z_mm.user_readback, 30.0)
        sim_run_engine.add_read_handler_for(
            beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION
        )
        yield beamstop
        beamline_utils.clear_devices()


@pytest.fixture
def oav_parameters_for_rotation(test_config_files) -> OAVParameters:
    return OAVParameters(oav_config_json=test_config_files["oav_config_json"])


@pytest.fixture()
def fake_create_rotation_devices(
    beamstop_i03: Beamstop,
    eiger: EigerDetector,
    smargon: Smargon,
    zebra: Zebra,
    detector_motion: DetectorMotion,
    backlight: Backlight,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    undulator: Undulator,
    aperture_scatterguard: ApertureScatterguard,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: DCM,
    robot: BartRobot,
    oav: OAV,
    sample_shutter: ZebraShutter,
    xbpm_feedback: XBPMFeedback,
):
    set_mock_value(smargon.omega.max_velocity, 131)
    undulator.set = MagicMock(return_value=NullStatus())
    return RotationScanComposite(
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_i03,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        flux=flux,
        smargon=smargon,
        undulator=undulator,
        aperture_scatterguard=aperture_scatterguard,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=zebra,
        robot=robot,
        oav=oav,
        sample_shutter=sample_shutter,
        xbpm_feedback=xbpm_feedback,
    )


@pytest.fixture
def test_fgs_params():
    return HyperionSpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json"
        )
    )


@pytest.fixture
def test_panda_fgs_params(test_fgs_params: HyperionSpecifiedThreeDGridScan):
    test_fgs_params.features.use_panda_for_gridscan = True
    return test_fgs_params


@pytest.fixture
def feature_flags():
    return HyperionFeatureFlags()


def dummy_params():
    dummy_params = HyperionSpecifiedThreeDGridScan(**default_raw_gridscan_params())
    return dummy_params


def dummy_params_2d():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/test_gridscan_param_defaults.json"
    )
    raw_params["z_steps"] = 1
    return HyperionSpecifiedThreeDGridScan(**raw_params)


@pytest.fixture
def test_full_grid_scan_params():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_grid_with_edge_detect_parameters.json"
    )
    return GridScanWithEdgeDetect(**params)


def dummy_rotation_data_collection_group_info():
    return DataCollectionGroupInfo(
        visit_string="cm31105-4",
        experiment_type="SAD",
        sample_id=364758,
    )
