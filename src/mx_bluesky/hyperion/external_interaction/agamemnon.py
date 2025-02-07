import dataclasses
import json

import requests

from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.common.utils.log import LOGGER

AGAMEMNON_URL = "http://agamemnon.diamond.ac.uk/"


@dataclasses.dataclass
class PinType:
    expected_number_of_crystals: int
    single_well_width_um: float
    additional_width_um: float = 0

    @property
    def full_width(self) -> float:
        """This is the "width" of the area where there may be samples.

        From a pin perspective this along the length of the pin but we use width here as
        we mount the sample at 90 deg to the optical camera."""
        return (
            self.expected_number_of_crystals * self.single_well_width_um
            + self.additional_width_um
        )


def _single_pin() -> PinType:
    return PinType(1, GridscanParamConstants.WIDTH_UM)


def _get_parameters_from_url(url: str) -> dict:
    response = requests.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    return json.loads(response.content)["collect"]


def _get_pin_type_from_agamemnon_parameters(parameters: dict) -> PinType:
    loop_type_name: str | None = parameters["sample"]["loopType"]
    if loop_type_name and loop_type_name.startswith("multipin"):
        shape = loop_type_name.split("-")[1].split("x")
        return PinType(int(shape[0]), float(shape[1]))
    if loop_type_name:
        LOGGER.warning(
            f"Agamemnon loop type of {loop_type_name} not recognised, assuming single pin"
        )
    return _single_pin()


def get_next_instruction(beamline: str) -> dict:
    return _get_parameters_from_url(AGAMEMNON_URL + f"getnextcollect/{beamline}")


def get_pin_type_from_agamemnon(beamline: str) -> PinType:
    params = get_next_instruction(beamline)
    return _get_pin_type_from_agamemnon_parameters(params)
