import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import Smargon, StubPosition

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import move_x_y_z
from mx_bluesky.hyperion.experiment_plans.common.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan


def change_aperture_then_move_to_xtal(
    best_hit: XRayCentreResult,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    parameters: HyperionThreeDGridScan | None = None,
):
    """For the given x-ray centring result,
    * Change the aperture so that the beam size is comparable to the crystal size
    * Centre on the centre-of-mass
    * Reset the stub offsets if specified by params"""
    if best_hit.bounding_box_mm is not None:
        bounding_box_size = numpy.abs(
            best_hit.bounding_box_mm[1] - best_hit.bounding_box_mm[0]
        )
        with TRACER.start_span("change_aperture"):
            yield from set_aperture_for_bbox_mm(
                aperture_scatterguard,
                bounding_box_size,
            )
    else:
        LOGGER.warning("No bounding box size received")

    # once we have the results, go to the appropriate position
    LOGGER.info("Moving to centre of mass.")
    with TRACER.start_span("move_to_result"):
        x, y, z = best_hit.centre_of_mass_mm
        yield from move_x_y_z(smargon, x, y, z, wait=True)

    # TODO support for setting stub offsets in multipin
    # https://github.com/DiamondLightSource/mx-bluesky/issues/552
    if parameters and parameters.FGS_params.set_stub_offsets:
        LOGGER.info("Recentring smargon co-ordinate system to this point.")
        yield from bps.mv(
            # See: https://github.com/bluesky/bluesky/issues/1809
            smargon.stub_offsets,  # type: ignore
            StubPosition.CURRENT_AS_CENTER,  # type: ignore
        )


def set_aperture_for_bbox_mm(
    aperture_device: ApertureScatterguard,
    bbox_size: list[float] | numpy.ndarray,
):
    """bbox_size represents the [x,y,z] lengths, in mm, of a bounding box
    containing a crystal. This discribes (in no particular order):
    * The maximum width a crystal occupies
    * The maximum height a crystal occupies
    * The maximum depth a crystal occupies
    Constructing a three dimensional cuboid, completely encapsulating the crystal."""

    # bbox_size is [x,y,z], for i03 we only care about x
    new_selected_aperture = (
        ApertureValue.MEDIUM if bbox_size[0] < 0.05 else ApertureValue.LARGE
    )
    LOGGER.info(
        f"Setting aperture to {new_selected_aperture} based on bounding box size {bbox_size}."
    )

    @bpp.set_run_key_decorator("change_aperture")
    @bpp.run_decorator(
        md={
            "subplan_name": "change_aperture",
            "aperture_size": new_selected_aperture.value,
        }
    )
    def set_aperture():
        yield from bps.abs_set(aperture_device, new_selected_aperture)

    yield from set_aperture()
