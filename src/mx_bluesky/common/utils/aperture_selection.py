import numpy

from mx_bluesky.common.parameters.components import AperturePolicy
from mx_bluesky.common.utils.log import LOGGER


def select_aperture_for_bbox_mm(
    bbox_size_mm: list[float] | numpy.ndarray, xtal_width_threshold_mm: float
) -> AperturePolicy:
    """Sets aperture size based on bbox_size.

    This function determines the aperture size needed to accommodate the bounding box
    of a crystal. The x-axis length of the bounding box is used, setting the aperture
    to Medium if this is less than the threshold size, and Large otherwise.

    Args:
        bbox_size_mm: The [x,y,z] lengths, in mm, of a bounding box
        containing a crystal. This describes (in no particular order):
        * The maximum width a crystal occupies
        * The maximum height a crystal occupies
        * The maximum depth a crystal occupies
        constructing a three-dimensional cuboid, completely encapsulating the crystal.
        xtal_width_threshold_mm (float): Threshold width below which medium aperture is selected
    Returns: The selected aperture policy
    """

    # bbox_size is [x,y,z], for i03 we only care about x
    new_selected_aperture = (
        AperturePolicy.MEDIUM
        if bbox_size_mm[0] < xtal_width_threshold_mm
        else AperturePolicy.LARGE
    )
    LOGGER.info(
        f"Setting aperture to {new_selected_aperture} based on bounding box size {bbox_size_mm}."
    )
    return new_selected_aperture
