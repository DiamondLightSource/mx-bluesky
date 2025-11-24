from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from deepdiff.diff import DeepDiff
from dodal.devices.zebra.zebra import RotationDirection
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
    IspybExperimentType,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    _get_parameters_from_url,
    _get_pin_type_from_agamemnon_collect_parameters,
    _SinglePin,
    create_parameters_from_agamemnon,
    get_agamemnon_url,
)
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

EXPECTED_ROBOT_LOAD_AND_CENTRE_PARAMS = {
    "storage_directory": "/dls/tmp/data/year/cm00000-0/auto/test/xraycentring",
    "snapshot_directory": Path(
        "/dls/tmp/data/year/cm00000-0/auto/test/xraycentring/snapshots"
    ),
    "file_name": "test_xtal",
    "demand_energy_ev": 12700.045934258673,
    "tip_offset_um": 300,
    "grid_width_um": 600,
    "omega_start_deg": 0,
    "chi_start_deg": 0,
    "transmission_frac": 1.0,
}

EXPECTED_ROTATION_PARAMS = {
    "storage_directory": "/dls/tmp/data/year/cm00000-0/auto/test",
    "snapshot_directory": Path("/dls/tmp/data/year/cm00000-0/auto/test/snapshots"),
    "file_name": "test_xtal",
    "demand_energy_ev": 12700.045934258673,
    "exposure_time_s": 0.002,
    "snapshot_omegas_deg": [0, 90, 180, 270],
    "comment": "Complete_P1_sweep1 ",
    "transmission_frac": 0.5,
    "ispyb_experiment_type": IspybExperimentType.CHARACTERIZATION,
    "rotation_scans": [
        {
            "omega_start_deg": 0.0,
            "phi_start_deg": 0.0,
            "scan_width_deg": 360,
            "rotation_direction": RotationDirection.POSITIVE,
            "chi_start_deg": 0.0,
            "sample_id": 12345,
        }
    ],
}

EXPECTED_PARAMETERS = {
    "visit": "cm00000-0",
    "detector_distance_mm": 180.8,
    "sample_id": 12345,
    "sample_puck": 1,
    "sample_pin": 1,
    "parameter_model_version": SemanticVersion.validate_from_str(
        str(PARAMETER_VERSION)
    ),
    "select_centres": {
        "name": "TopNByMaxCount",
        "n": 1,
    },
    "robot_load_then_centre": EXPECTED_ROBOT_LOAD_AND_CENTRE_PARAMS,
    "multi_rotation_scan": EXPECTED_ROTATION_PARAMS,
}


@pytest.fixture()
def use_real_agamemnon(request):
    url = getattr(request, "param", None)

    def get_injected_url(url, beamline):
        return _get_parameters_from_url(url)

    with patch(
        "mx_bluesky.hyperion.external_interaction.agamemnon._get_next_instruction",
        side_effect=partial(get_injected_url, url),
    ) as patched_get_next_instruction:
        yield patched_get_next_instruction


@pytest.mark.requires(external="agamemnon")
def test_given_test_agamemnon_instruction_then_returns_none_loop_type():
    params = _get_parameters_from_url(get_agamemnon_url() + "/example/collect")
    loop_type = _get_pin_type_from_agamemnon_collect_parameters(params["collect"])
    assert loop_type == _SinglePin()


@pytest.mark.requires(external="agamemnon")
@pytest.mark.parametrize(
    "use_real_agamemnon", [f"{get_agamemnon_url()}/example/collect"], indirect=True
)
def test_given_test_agamemnon_instruction_then_load_centre_collect_parameters_populated(
    use_real_agamemnon: MagicMock,
):
    load_centre_collect = create_parameters_from_agamemnon()
    expected_parameter_model = [
        LoadCentreCollect.model_validate(EXPECTED_PARAMETERS),
        LoadCentreCollect.model_validate(EXPECTED_PARAMETERS),
    ]
    expected_parameter_model[1].robot_load_then_centre.chi_start_deg = 30.0
    expected_parameter_model[1].multi_rotation_scan.rotation_scans[
        0
    ].chi_start_deg = 30.0
    # Currently agamemnon example json has two different experiment types, although this is not
    # realistic
    expected_parameter_model[
        1
    ].multi_rotation_scan.ispyb_experiment_type = IspybExperimentType.OSC
    difference = DeepDiff(
        load_centre_collect,
        expected_parameter_model,
    )
    assert not difference


@pytest.mark.requires(external="agamemnon")
@pytest.mark.parametrize(
    "use_real_agamemnon", [f"{get_agamemnon_url()}/example/wait"], indirect=True
)
def test_create_parameters_from_agamemnon_decodes_wait_instruction(
    use_real_agamemnon: MagicMock,
):
    params = create_parameters_from_agamemnon()
    difference = DeepDiff(
        params,
        [
            Wait.model_validate(
                {
                    "duration_s": 10.0,
                    "parameter_model_version": SemanticVersion.validate_from_str(
                        str(PARAMETER_VERSION)
                    ),
                }
            )
        ],
    )
    assert not difference
