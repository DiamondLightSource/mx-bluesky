import pytest

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


def test_params_load_from_file(params):
    assert params.x_start_um is None
    assert params.y_start_um is None
    assert params.z_start_um is None

    complete_params = RotationScanParameters.from_file(
        "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/complete_example_params.json"
    )
    assert complete_params.x_start_um is not None
    assert complete_params.y_start_um is not None
    assert complete_params.z_start_um is not None

    assert complete_params.get_num_images() == 3600


def test_params_validation():
    with pytest.raises(ValueError) as exc:
        params = RotationScanParameters.from_file(  # noqa
            "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/bad_params_acq_time_too_short.json"
        )
    assert (
        exc.value.errors()[0]["msg"]
        == "Acquisition time must not be shorter than exposure time!"
    )
