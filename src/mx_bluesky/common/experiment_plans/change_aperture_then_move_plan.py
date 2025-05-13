import bluesky.plan_stubs as bps
import numpy
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import Smargon, StubPosition

from mx_bluesky.common.device_setup_plans.manipulate_sample import move_x_y_z
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.common.xrc_result import XRayCentreResult


def change_aperture_then_move_to_xtal(
    best_hit: XRayCentreResult,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    set_stub_offsets: bool | None = None,
):
    """For the given x-ray centring result,
    * Change the aperture so that the beam size is comparable to the crystal size
    * Centre on the centre-of-mass
    * Reset the stub offsets if specified by params"""
    bounding_box_size = numpy.abs(
        best_hit.bounding_box_mm[1] - best_hit.bounding_box_mm[0]
    )
    yield from set_aperture_for_bbox_mm(
        aperture_scatterguard,
        bounding_box_size,
    )

    # once we have the results, go to the appropriate position
    LOGGER.info("Moving to centre of mass.")
    with TRACER.start_span("move_to_result"):
        x, y, z = best_hit.centre_of_mass_mm
        yield from move_x_y_z(smargon, x, y, z, wait=True)

    # TODO support for setting stub offsets in multipin
    # https://github.com/DiamondLightSource/mx-bluesky/issues/552
    if set_stub_offsets:
        LOGGER.info("Recentring smargon co-ordinate system to this point.")
        yield from bps.mv(smargon.stub_offsets, StubPosition.CURRENT_AS_CENTER)


def set_aperture_for_bbox_mm(
    aperture_device: ApertureScatterguard,
    bbox_size_mm: list[float] | numpy.ndarray,
):
    """Sets aperture size based on bbox_size.

    This function determines the aperture size needed to accommodate the bounding box
    of a crystal. The x-axis length of the bounding box is used, setting the aperture
    to Medium if this is less than 50um, and Large otherwise.

    Args:
        aperture_device: The aperture scatter guard device we are controlling.
        bbox_size_mm: The [x,y,z] lengths, in mm, of a bounding box
        containing a crystal. This describes (in no particular order):
        * The maximum width a crystal occupies
        * The maximum height a crystal occupies
        * The maximum depth a crystal occupies
        constructing a three dimensional cuboid, completely encapsulating the crystal.

    Yields:
        Iterator[MsgGenerator]
    """

    # bbox_size is [x,y,z], for i03 we only care about x
    new_selected_aperture = (
        ApertureValue.MEDIUM if bbox_size_mm[0] < 0.05 else ApertureValue.LARGE
    )
    LOGGER.info(
        f"Setting aperture to {new_selected_aperture} based on bounding box size {bbox_size_mm}."
    )

    yield from bps.abs_set(aperture_device.selected_aperture, new_selected_aperture)
