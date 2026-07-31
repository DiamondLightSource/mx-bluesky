import pytest

from mx_bluesky.common.parameters.rotation import images_in_sweep


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        (360, 0.1, 3600),
        (90, 0.2, 450),
        (0.1, 0.1, 1),
        (360, 0.05, 7200),
    ],
)
def test_a_sweep_that_divides_exactly_gives_the_whole_number_of_images(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        # Each of these divides exactly in decimal but lands just under a whole number in
        # floating point, so truncating the quotient would collect one image too few.
        (2.15, 0.05, 43),
        (4.05, 0.05, 81),
        (8.1, 0.05, 162),
    ],
)
def test_floating_point_error_does_not_cost_an_image(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        (10, 0.3, 33),
        (1, 0.7, 1),
        (0.5, 0.3, 1),
    ],
)
def test_a_sweep_that_does_not_divide_exactly_rounds_down(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    # A partial image at the end is not collected, so the tolerance must not round up.
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected
