import dataclasses
import json
import re
from typing import TypeVar

import requests
from dodal.utils import get_beamline_name

from mx_bluesky.common.parameters.components import WithVisit
from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

T = TypeVar("T", bound=WithVisit)
AGAMEMNON_URL = "http://agamemnon.diamond.ac.uk/"
MULTIPIN_PREFIX = "multipin"
MULTIPIN_FORMAT_DESC = "Expected multipin format is multipin_{number_of_wells}x{well_size}+{distance_between_tip_and_first_well}"
MULTIPIN_REGEX = rf"^{MULTIPIN_PREFIX}_(\d+)x(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)$"


@dataclasses.dataclass
class PinType:
    expected_number_of_crystals: int
    single_well_width_um: float
    tip_to_first_well_um: float = 0

    @property
    def full_width(self) -> float:
        """This is the "width" of the area where there may be samples.

        From a pin perspective this is along the length of the pin but we use width here as
        we mount the sample at 90 deg to the optical camera.

        We calculate the full width by adding all the gaps between wells then assuming
        there is a buffer of {tip_to_first_well_um} either side too. In reality the
        calculation does not need to be very exact as long as we get a width that's good
        enough to use for optical centring and XRC grid size.
        """
        return (self.expected_number_of_crystals - 1) * self.single_well_width_um + (
            2 * self.tip_to_first_well_um
        )


class SinglePin(PinType):
    def __init__(self):
        super().__init__(1, GridscanParamConstants.WIDTH_UM)

    @property
    def full_width(self) -> float:
        return self.single_well_width_um


def _get_parameters_from_url(url: str) -> dict:
    response = requests.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    response_json = json.loads(response.content)
    try:
        return response_json["collect"]
    except KeyError as e:
        raise Exception(f"Unexpected json from agamemnon: {response_json}") from e


def _get_pin_type_from_agamemnon_parameters(parameters: dict) -> PinType:
    loop_type_name: str | None = parameters["sample"]["loopType"]
    if loop_type_name:
        regex_search = re.search(MULTIPIN_REGEX, loop_type_name)
        if regex_search:
            wells, well_size, tip_to_first_well = regex_search.groups()
            return PinType(int(wells), float(well_size), float(tip_to_first_well))
        else:
            loop_type_message = (
                f"Agamemnon loop type of {loop_type_name} not recognised"
            )
            if loop_type_name.startswith(MULTIPIN_PREFIX):
                raise ValueError(f"{loop_type_message}. {MULTIPIN_FORMAT_DESC}")
            LOGGER.warning(f"{loop_type_message}, assuming single pin")
    return SinglePin()


def get_next_instruction(beamline: str) -> dict:
    return _get_parameters_from_url(AGAMEMNON_URL + f"getnextcollect/{beamline}")


def get_pin_type_from_agamemnon(beamline: str) -> PinType:
    params = get_next_instruction(beamline)
    return _get_pin_type_from_agamemnon_parameters(params)


def update_params_from_agamemnon(parameters: T) -> T:
    try:
        beamline_name = get_beamline_name("i03")
        pin_type = get_pin_type_from_agamemnon(beamline_name)
        if isinstance(parameters, LoadCentreCollect):
            parameters.robot_load_then_centre.tip_offset_um = pin_type.full_width / 2
            parameters.robot_load_then_centre.grid_width_um = pin_type.full_width
            parameters.select_centres.n = pin_type.expected_number_of_crystals
    except Exception as e:
        LOGGER.warning(f"Failed to get pin type from agamemnon, using single pin {e}")
    return parameters
