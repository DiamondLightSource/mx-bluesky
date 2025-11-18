import math
from math import asin

from scanspec.core import AxesPoints, Axis
from scipy.constants import physical_constants

from mx_bluesky.common.utils.log import LOGGER

hc_in_ev_and_angstrom: float = (
    physical_constants["speed of light in vacuum"][0]
    * physical_constants["Planck constant in eV/Hz"][0]
    * 1e10  # Angstroms per metre
)


def interconvert_ev_angstrom(wavelength_or_energy: float) -> float:
    return hc_in_ev_and_angstrom / wavelength_or_energy


def convert_ev_to_angstrom(hv: float) -> float:
    return interconvert_ev_angstrom(hv)


def convert_angstrom_to_ev(wavelength: float) -> float:
    return interconvert_ev_angstrom(wavelength)


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
    wavelength_a = convert_ev_to_angstrom(energy_kev * 1000)
    d = d_a
    return asin(wavelength_a / (2 * d)) * 180 / math.pi


def fix_transmission_and_exposure_time_for_current_wavelength(
    current_wavelength_a: float,
    assumed_wavelength_a_from_settings: float,
    requested_trans_frac: float = 100,
    requested_exposure_time_s: float = 0.004,
) -> tuple[float, float]:
    """
    Calculates an exposure time and transmission fraction for XRC which will provide a good signal
    on the detector by using a known good wavelength, comparing it to the beamlines current wavelength,
    then scaling accordingly.

    Args:
        current_wavelength_a: Current energy of the beamline in angstroms.
        assumed_wavelength_a_from_settings: The known "good" wavelength. This should be read from
            'gda.px.expttable.default.wavelength' in GDA's domain.properties, via the config server.
        requested_trans_frac: Requested transmission fraction to use.
        requested_exposure_time_s: Requested exposure time to use.

    Returns:
        The scaled transmission fraction and exposure time respectively, in a tuple.
    """

    wavelength_scale = (assumed_wavelength_a_from_settings / current_wavelength_a) ** 2

    # Transmission frac needed to get ideal signal
    ideal_trans_frac = requested_trans_frac * wavelength_scale
    if ideal_trans_frac <= 1:
        new_trans_frac = ideal_trans_frac
        new_exposure_time_s = requested_exposure_time_s
    else:
        # If the scaling would result in transmission fraction > 1,
        # cap it to 1, find remaining scaling needed, and apply it
        # to exposure time instead.
        new_trans_frac = 1
        scaling_applied_to_trans = new_trans_frac / requested_trans_frac
        remaining_scaling_needed = wavelength_scale / scaling_applied_to_trans
        new_exposure_time_s = requested_exposure_time_s * remaining_scaling_needed

    LOGGER.info(
        f"Fixing transmission fraction to {new_trans_frac} and exposure time to {new_exposure_time_s}s"
    )

    # Exposure time in FGS IOC is in ms, and must be an integer, so round it here
    return new_trans_frac, round(new_exposure_time_s, 3)
