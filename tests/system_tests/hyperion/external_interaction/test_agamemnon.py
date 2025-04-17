from pathlib import Path

from deepdiff.diff import DeepDiff
from dodal.devices.zebra.zebra import RotationDirection
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
    IspybExperimentType,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    AGAMEMNON_URL,
    SinglePin,
    _get_parameters_from_url,
    get_pin_type_from_agamemnon_parameters,
    populate_parameters_from_agamemnon,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import (
    RotationScanPerSweep,
)

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
    "features": {"use_gpu_results": True},
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
        RotationScanPerSweep(
            omega_start_deg=0.0,
            phi_start_deg=0.0,
            scan_width_deg=360,
            rotation_direction=RotationDirection.POSITIVE,
            chi_start_deg=0.0,
        )
    ],
}

EXPECTED_PARAMETERS = LoadCentreCollect.model_validate(
    {
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
)


def test_given_test_agamemnon_instruction_then_returns_none_loop_type():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    loop_type = get_pin_type_from_agamemnon_parameters(params)
    assert loop_type == SinglePin()


def test_given_test_agamemnon_instruction_then_load_centre_collect_parameters_populated():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    load_centre_collect = populate_parameters_from_agamemnon(params)
    difference = DeepDiff(
        load_centre_collect,
        EXPECTED_PARAMETERS,
    )
    assert not difference
