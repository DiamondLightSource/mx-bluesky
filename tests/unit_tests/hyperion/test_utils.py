import math

import pytest

from mx_bluesky.common.utils.utils import (
    convert_angstrom_to_eV,
    convert_eV_to_angstrom,
    energy_to_bragg_angle,
)

SI_111_SPACING_ANGSTROMS = 3.13475

test_wavelengths = [1.620709, 1.2398425, 0.9762539, 0.8265616, 0.68880138]
test_energies = [7650, 10000, 12700, 15000, 18000]


@pytest.mark.parametrize(
    "test_wavelength, test_energy",
    list(zip(test_wavelengths, test_energies, strict=False)),
)
def test_ev_to_a_converter(test_wavelength, test_energy):
    assert convert_eV_to_angstrom(test_energy) == pytest.approx(test_wavelength)


@pytest.mark.parametrize(
    "test_wavelength, test_energy",
    list(zip(test_wavelengths, test_energies, strict=False)),
)
def test_a_to_ev_converter(test_wavelength, test_energy):
    assert convert_angstrom_to_eV(test_wavelength) == pytest.approx(test_energy)


@pytest.mark.parametrize(
    "input_energy_kev, expected_bragg_angle_deg",
    [[7, 16.41], [8, 14.31], [11, 10.35], [12.3, 9.25], [15, 7.57]],
)
def test_energy_to_bragg_angle(
    input_energy_kev: float, expected_bragg_angle_deg: float
):
    assert math.isclose(
        energy_to_bragg_angle(input_energy_kev, SI_111_SPACING_ANGSTROMS),
        expected_bragg_angle_deg,
        abs_tol=0.01,
    )
