from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.hyperion.blueapi_plans.parameters import (
    LoadCentreCollectParams,
    load_centre_collect_to_internal,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ....conftest import raw_params_from_file


def test_map_external_to_internal_parameters(tmp_path):
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/external_load_centre_collect_params.json",
        tmp_path,
    )
    external_params = LoadCentreCollectParams(**raw_params)
    expected_internal = LoadCentreCollect(
        **(raw_params | {"parameter_model_version": get_param_version()})
    )
    actual_internal = load_centre_collect_to_internal(external_params)
    assert expected_internal == actual_internal
