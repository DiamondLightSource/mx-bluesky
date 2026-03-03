from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i02_1
from dodal.beamlines.i02_1 import ZebraFastGridScanTwoD
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.common_dcm import DoubleCrystalMonochromatorBase
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import BaseUndulator
from dodal.devices.zebra.zebra import Zebra
from pydantic import ValidationError

from mx_bluesky.beamlines.i02_1.composites import I02_1FgsParams
from mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan import (
    FlyScanXRayCentreComposite,
    construct_i02_1_specific_features,
    i02_1_gridscan_plan,
)
from mx_bluesky.beamlines.i02_1.parameters.gridscan import SpecifiedTwoDGridScan
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    populate_data_collection_group,
    populate_remaining_data_collection_info,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.common.parameters.device_composites import (
    GonioWithOmega,
)


@pytest.fixture
def zebra_fgs_two_d() -> ZebraFastGridScanTwoD:
    device = i02_1.zebra_fast_grid_scan.build(connect_immediately=True, mock=True)

    return device


@pytest.fixture
def fgs_composite(
    eiger: EigerDetector,
    synchrotron: Synchrotron,
    smargon: GonioWithOmega,
    zebra_fgs_two_d: ZebraFastGridScanTwoD,
    dcm: DoubleCrystalMonochromatorBase,
    attenuator: ReadOnlyAttenuator,
    flux: Flux,
    undulator: BaseUndulator,
    s4_slit_gaps: S4SlitGaps,
    zebra: Zebra,
) -> FlyScanXRayCentreComposite:
    return FlyScanXRayCentreComposite(
        eiger,
        synchrotron,
        smargon,
        zebra,
        zebra_fgs_two_d,
        dcm,
        attenuator,
        flux,
        undulator,
        s4_slit_gaps,
    )


class SpecifiedTwoDTest(SpecifiedTwoDGridScan):
    # Skip parent validation for easier testing
    def _check_lengths_are_same(self):  # type: ignore
        return self


@pytest.mark.parametrize(
    "y_starts_um, z_starts_um, omega_starts_deg, y_step_sizes_um, y_steps, should_raise",
    [
        ([1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], True),
        ([1], [1], [1], [1, 1], [1], True),
        ([1], [1], [1, 1], [1], [1], True),
        ([1], [1], [1], [1], [1], False),
    ],
)
def test_two_d_grid_scan_validation(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[int],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    should_raise: bool,
    tmp_path,
):
    def create_params():
        SpecifiedTwoDTest(
            x_start_um=0,
            y_starts_um=y_starts_um,
            z_starts_um=z_starts_um,
            y_step_sizes_um=y_step_sizes_um,
            omega_starts_deg=omega_starts_deg,
            parameter_model_version=get_param_version(),
            sample_id=0,
            visit="visit",
            file_name="test_file",
            storage_directory=str(tmp_path),
            x_steps=5,
            y_steps=y_steps,
        )

    if should_raise:
        with pytest.raises(ValidationError, match="must be length 1 for 2D scans"):
            create_params()
    else:
        create_params()


@patch(
    "mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan.create_gridscan_callbacks",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan.construct_i02_1_specific_features",
)
@patch(
    "mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan.common_flyscan_xray_centre",
)
def test_i02_1_flyscan_xray_centre_in_re(
    mock_common_scan: MagicMock,
    mock_create_features: MagicMock,
    run_engine: RunEngine,
    fgs_params_two_d: I02_1FgsParams,
    fgs_composite: FlyScanXRayCentreComposite,
):
    expected_features = construct_i02_1_specific_features(
        fgs_composite, fgs_params_two_d
    )

    mock_create_features.return_value = expected_features
    run_engine(i02_1_gridscan_plan(fgs_params_two_d, fgs_composite))
    mock_common_scan.assert_called_once_with(
        fgs_composite, fgs_params_two_d, expected_features
    )


@patch(
    "mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan.construct_i02_1_specific_features",
)
@patch(
    "mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan.common_flyscan_xray_centre",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback.StoreInIspyb"
)
def test_ispyb_activated_correct_params(
    mock_store_ispyb: MagicMock,
    mock_create_features: MagicMock,
    run_engine: RunEngine,
    fgs_params_two_d: I02_1FgsParams,
    fgs_composite: FlyScanXRayCentreComposite,
):
    mock_ispyb = MagicMock()

    mock_store_ispyb.return_value = mock_ispyb
    expected_features = construct_i02_1_specific_features(
        fgs_composite, fgs_params_two_d
    )
    run_engine.md["data"] = {}

    mock_create_features.return_value = expected_features

    run_engine(i02_1_gridscan_plan(fgs_params_two_d, fgs_composite))
    initial_group_info = populate_data_collection_group(fgs_params_two_d)
    initial_group_info.comments = f"Diffraction grid scan of {fgs_params_two_d.x_steps} by {fgs_params_two_d.y_steps[0]}.Zocalo processing took 0.00 s."
    initial_scan_info = ScanDataInfo(
        data_collection_info=populate_remaining_data_collection_info(
            "MX-Bluesky: Xray centring 1/1 -",
            None,
            DataCollectionInfo(),
            fgs_params_two_d,
        )
    )
    mock_ispyb.begin_deposition.assert_called_once_with(
        initial_group_info, [initial_scan_info]
    )
