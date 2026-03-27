import pytest

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    MultiSamplePinTypeParam,
    SingleSamplePinTypeParam,
    load_centre_collect_to_internal,
    pin_type_to_tip_offset_and_grid_width,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ....conftest import raw_params_from_file


def test_map_external_to_internal_parameters(tmp_path):
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/external_load_centre_collect_params.json",
        tmp_path,
    )
    external_params = LoadCentreCollectParams(**raw_params)
    raw_params["robot_load_then_centre"]["tip_offset_um"] = 300.0
    expected_internal = LoadCentreCollect(
        **(raw_params | {"parameter_model_version": get_param_version()})
    )
    actual_internal = load_centre_collect_to_internal(external_params)
    assert expected_internal == actual_internal


def test_map_external_to_internal_multisample_pin(tmp_path):
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/external_load_centre_collect_params_multipin.json",
        tmp_path,
    )
    external_params = LoadCentreCollectParams(**raw_params)
    actual_internal = load_centre_collect_to_internal(external_params)

    assert actual_internal.robot_load_then_centre.grid_width_um == 520
    assert actual_internal.robot_load_then_centre.tip_offset_um == 260


def test_pin_type_to_tip_offset_and_grid_width_raises_value_error_on_unrecognised_type():
    with pytest.raises(ValueError):
        pin_type_to_tip_offset_and_grid_width(None)  # type: ignore


def test_pin_type_to_tip_offset_and_grid_width_converts_single_sample_pin():
    tip_offset, grid_width = pin_type_to_tip_offset_and_grid_width(
        SingleSamplePinTypeParam()
    )
    assert tip_offset == 300
    assert grid_width == 600


@pytest.mark.parametrize(
    "num_wells, well_width, buffer, expected_width",
    [
        (3, 500, 0, 1000),
        (6, 50, 100, 450),
        (2, 800, 50, 900),
    ],
)
def test_given_various_pin_formats_then_pin_width_as_expected(
    num_wells, well_width, buffer, expected_width
):
    pin = MultiSamplePinTypeParam(
        wells=num_wells, well_size_um=well_width, tip_to_first_well_um=buffer
    )
    tip_offset, grid_width = pin_type_to_tip_offset_and_grid_width(pin)
    assert tip_offset == expected_width / 2
    assert grid_width == expected_width
