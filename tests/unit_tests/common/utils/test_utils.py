from mx_bluesky.common.utils.utils import (
    fix_transmission_and_exposure_time_for_current_wavelength,
)

ASSUMED_WAVELENGTH = 0.95373


def test_fix_transmission_and_exposure_time_does_nothing_given_assumed_energy():
    transmission = 0.55
    exposure_time_s = 0.03
    assert fix_transmission_and_exposure_time_for_current_wavelength(
        ASSUMED_WAVELENGTH, ASSUMED_WAVELENGTH, transmission, exposure_time_s
    ) == (transmission, exposure_time_s)


def test_fix_transmission_and_exposure_time_different_wavelength_reduces_transmission_only():
    transmission = 0.55
    exposure_time_s = 0.03
    wavelength_to_use = ASSUMED_WAVELENGTH * 2
    expected_transmission = transmission * (
        (ASSUMED_WAVELENGTH / wavelength_to_use) ** 2
    )
    assert fix_transmission_and_exposure_time_for_current_wavelength(
        wavelength_to_use, ASSUMED_WAVELENGTH, transmission, exposure_time_s
    ) == (expected_transmission, exposure_time_s)


def test_fix_transmission_and_exposure_time_low_wavelength_lowers_exposure_time_if_transmission_is_maxed():
    transmission = 0.95
    exposure_time_s = 0.03
    wavelength_to_use = ASSUMED_WAVELENGTH / 2
    expected_transmission = 1
    expected_exposure_time = round(
        transmission
        * ((ASSUMED_WAVELENGTH / wavelength_to_use) ** 2)
        * exposure_time_s,
        3,
    )
    assert fix_transmission_and_exposure_time_for_current_wavelength(
        wavelength_to_use, ASSUMED_WAVELENGTH, transmission, exposure_time_s
    ) == (expected_transmission, expected_exposure_time)


def test_fix_transmission_and_exposure_time_rounds_exposure_time_to_ms():
    exposure_time_s = 0.234873469
    transmission = 1
    assert fix_transmission_and_exposure_time_for_current_wavelength(
        ASSUMED_WAVELENGTH, ASSUMED_WAVELENGTH, transmission, exposure_time_s
    ) == (transmission, round(exposure_time_s, 3))
