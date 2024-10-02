from abc import abstractmethod
from typing import Protocol

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import Smargon, StubPosition

from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import move_x_y_z
from mx_bluesky.hyperion.experiment_plans.common.flyscan_result import FlyscanResult
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.gridscan import ThreeDGridScan
from mx_bluesky.hyperion.tracing import TRACER


class CentringComposite(Protocol):
    aperture_scatterguard: ApertureScatterguard

    @property
    @abstractmethod
    def sample_motors(self) -> Smargon:
        pass


def change_aperture_then_centre(
    best_hit: FlyscanResult,
    composite: CentringComposite,
    parameters: ThreeDGridScan | None = None,
):
    """For the given flyscan result,
    * Change the aperture to something sensible
    * Centre on the centre-of-mass
    * Reset the stub offsets if specified by params"""
    if best_hit.bounding_box_mm is not None:
        bounding_box_size = numpy.abs(
            best_hit.bounding_box_mm[1] - best_hit.bounding_box_mm[0]
        )
        with TRACER.start_span("change_aperture"):
            yield from _set_aperture_for_bbox_mm(
                composite.aperture_scatterguard, bounding_box_size
            )
    else:
        LOGGER.warning("No bounding box size received")

    # once we have the results, go to the appropriate position
    LOGGER.info("Moving to centre of mass.")
    with TRACER.start_span("move_to_result"):
        x, y, z = best_hit.centre_of_mass_mm
        yield from move_x_y_z(composite.sample_motors, x, y, z, wait=True)

    # TODO support for setting stub offsets in multipin mx-bluesky 552
    if parameters and parameters.FGS_params.set_stub_offsets:
        LOGGER.info("Recentring smargon co-ordinate system to this point.")
        yield from bps.mv(
            composite.sample_motors.stub_offsets, StubPosition.CURRENT_AS_CENTER
        )


def _set_aperture_for_bbox_mm(
    aperture_device: ApertureScatterguard, bbox_size_mm: list[float] | numpy.ndarray
):
    # TODO confirm correction factor see mx-bluesky 231
    ASSUMED_BOX_SIZE_MM = 0.020
    bbox_size_boxes = [round(mm / ASSUMED_BOX_SIZE_MM) for mm in bbox_size_mm]
    yield from set_aperture_for_bbox_size(aperture_device, bbox_size_boxes)


def set_aperture_for_bbox_size(
    aperture_device: ApertureScatterguard,
    bbox_size: list[int] | numpy.ndarray,
):
    # bbox_size is [x,y,z], for i03 we only care about x
    new_selected_aperture = (
        ApertureValue.MEDIUM if bbox_size[0] < 2 else ApertureValue.LARGE
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
