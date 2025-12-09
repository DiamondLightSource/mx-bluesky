from mx_bluesky.common.parameters.rotation import SingleRotationScan
from tests.conftest import raw_params_from_file


def get_good_single_rotation_params(tmp_path):
    params = raw_params_from_file(
        "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/test_good_rotation_params.json",
        tmp_path,
    )

    return SingleRotationScan(**params)
