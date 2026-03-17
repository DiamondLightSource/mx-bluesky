import dataclasses

from mx_bluesky.common.parameters.constants import GridscanParamConstants


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
