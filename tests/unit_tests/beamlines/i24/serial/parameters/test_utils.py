from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters import get_chip_format, get_chip_map
from mx_bluesky.beamlines.i24.serial.parameters.utils import EmptyMapError


@pytest.mark.parametrize(
    "chip_type, expected_num_blocks, expected_step_size, expected_num_steps",
    [(0, 8, 0.125, 20), (1, 1, 0.6, 25), (3, 1, 0.125, 20)],
)
def test_get_chip_format_for_oxford_chips(
    chip_type: int,
    expected_num_blocks: int,
    expected_step_size: float,
    expected_num_steps: int,
):
    test_defaults = get_chip_format(ChipType(chip_type)).model_dump()

    assert (
        test_defaults["x_num_steps"] == expected_num_steps
        and test_defaults["x_num_steps"] == test_defaults["y_num_steps"]
    )
    assert test_defaults["y_blocks"] == expected_num_blocks
    assert test_defaults["x_step_size"] == expected_step_size


@patch("mx_bluesky.beamlines.i24.serial.parameters.utils.caget")
def test_get_chip_format_for_custom_chips(fake_caget: MagicMock):
    fake_caget.side_effect = ["10", "2", "0.2", "0.2"]
    test_chip_type = ChipType(2)
    test_defaults = get_chip_format(test_chip_type).model_dump()

    assert test_defaults["x_num_steps"] == 10
    assert test_defaults["y_num_steps"] == 2
    assert test_defaults["x_step_size"] == 0.2 and test_defaults["y_step_size"] == 0.2
    assert test_defaults["y_blocks"] == 1


@patch(
    "mx_bluesky.beamlines.i24.serial.parameters.utils.OXFORD_BLOCKS_PVS",
    new=["block1", "block2", "block3"],
)
@patch("mx_bluesky.beamlines.i24.serial.parameters.utils.caget")
def test_get_chip_map_raises_error_for_empty_map(fake_caget: MagicMock):
    fake_caget.side_effect = [0, 0, 0]
    with pytest.raises(EmptyMapError):
        get_chip_map()


@patch(
    "mx_bluesky.beamlines.i24.serial.parameters.utils.OXFORD_BLOCKS_PVS",
    new=["block1", "block2", "block3"],
)
@patch("mx_bluesky.beamlines.i24.serial.parameters.utils.caget")
def test_get_chip_map(fake_caget: MagicMock):
    fake_caget.side_effect = ["1", "0", "1"]

    chip_map = get_chip_map()

    assert len(chip_map) == 2
    assert chip_map == [1, 3]


def test_get_chip_format_for_custom_from_web_ui_fails_if_no_data_passed():
    with pytest.raises(ValueError):
        get_chip_format(ChipType.Custom, None, "web")


def test_get_chip_format_for_custom_from_web_ui():
    test_custom_chip = ChipType["Custom"]
    test_format_from_web = [10, 2, 0.2, 0.2]
    chip_format = get_chip_format(
        test_custom_chip, test_format_from_web, "web"
    ).model_dump()

    assert chip_format["x_num_steps"] == 10
    assert chip_format["y_num_steps"] == 2
    assert chip_format["x_step_size"] == 0.2 and chip_format["y_step_size"] == 0.2
    assert chip_format["y_blocks"] == 1
