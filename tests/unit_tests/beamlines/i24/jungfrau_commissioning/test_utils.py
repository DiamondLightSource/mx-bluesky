import pytest

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


def test_params_load_from_file():
    minimal_params = RotationScanParameters.from_file("example_params.json")
    assert minimal_params.x is None
    assert minimal_params.y is None
    assert minimal_params.z is None

    complete_params = RotationScanParameters.from_file("example_complete_params.json")
    assert complete_params.x is not None
    assert complete_params.y is not None
    assert complete_params.z is not None

    assert complete_params.get_num_images() == 3600


def test_params_validation():
    with pytest.raises(ValueError) as exc:
        params = RotationScanParameters.from_file(  # noqa
            "tests/test_data/bad_params_acq_time_too_short.json"
        )
    assert (
        exc.value.errors()[0]["msg"]
        == "Acquisition time must not be shorter than exposure time!"
    )
