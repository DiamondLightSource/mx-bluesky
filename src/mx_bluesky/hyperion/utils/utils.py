import math
from math import asin

from scanspec.core import AxesPoints, Axis
from scipy.constants import physical_constants

hc_in_eV_and_Angstrom: float = (
    physical_constants["speed of light in vacuum"][0]
    * physical_constants["Planck constant in eV/Hz"][0]
    * 1e10  # Angstroms per metre
)


def interconvert_eV_Angstrom(wavelength_or_energy: float) -> float:
    return hc_in_eV_and_Angstrom / wavelength_or_energy


def convert_eV_to_angstrom(hv: float) -> float:
    return interconvert_eV_Angstrom(hv)


def convert_angstrom_to_eV(wavelength: float) -> float:
    return interconvert_eV_Angstrom(wavelength)


def number_of_frames_from_scan_spec(scan_points: AxesPoints[Axis]):
    ax = list(scan_points.keys())[0]
    return len(scan_points[ax])


def energy_to_bragg_angle(energy_kev: float, d_a: float) -> float:
    """Compute the bragg angle given the energy in kev.

    Args:
        energy_kev:  The energy in keV
        d_a:         The lattice spacing in Angstroms
    Returns:
        The bragg angle in degrees
    """
    wavelength_a = convert_eV_to_angstrom(energy_kev * 1000)
    d = d_a
    return asin(wavelength_a / (2 * d)) * 180 / math.pi
