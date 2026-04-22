from typing import Any

import pytest

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    load_centre_collect_to_internal,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ....conftest import raw_params_from_file


@pytest.fixture
def load_centre_collect_params_raw(tmp_path) -> dict[str, Any]:
    return raw_params_from_file(
        "tests/test_data/parameter_json_files/external_load_centre_collect_params.json",
        tmp_path,
    )


def test_map_external_to_internal_parameters(load_centre_collect_params_raw):
    raw_params = load_centre_collect_params_raw
    external_params = LoadCentreCollectParams(**raw_params)
    expected_internal = LoadCentreCollect(
        **(raw_params | {"parameter_model_version": get_param_version()})
    )
    actual_internal = load_centre_collect_to_internal(external_params)
    assert expected_internal == actual_internal


def test_load_centre_collect_current_position_aperture_not_supported(
    load_centre_collect_params_raw,
):
    load_centre_collect_params_raw["multi_rotation_scan"]["selected_aperture"] = (
        "CURRENT_POSITION"
    )
    with pytest.raises(
        ValueError, match="selected_aperture of CURRENT_POSITION is not supported"
    ):
        LoadCentreCollectParams(**load_centre_collect_params_raw)
