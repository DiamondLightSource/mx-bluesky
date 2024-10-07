import dataclasses
from collections.abc import Sequence

from blueapi.core import BlueskyContext
from bluesky.preprocessors import subs_decorator
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon

import mx_bluesky.hyperion.experiment_plans.common.flyscan_result as flyscan_result
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    FlyscanEventHandler,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_flyscan,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
    multi_rotation_scan,
)
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.utils.context import device_composite_from_context


@dataclasses.dataclass
class LoadCentreCollectComposite(RobotLoadThenCentreComposite, RotationScanComposite):
    """Composite that provides access to the required devices."""

    @property
    def sample_motors(self) -> Smargon:
        return self.smargon


def create_devices(context: BlueskyContext) -> LoadCentreCollectComposite:
    """Create the necessary devices for the plan."""
    return device_composite_from_context(context, LoadCentreCollectComposite)


def load_centre_collect_full_plan(
    composite: LoadCentreCollectComposite,
    params: LoadCentreCollect,
    oav_params: OAVParameters | None = None,
):
    """Attempt a complete data collection experiment, consisting of the following:
    * Load the sample if necessary
    * Move to the specified goniometer start angles
    * Perform optical centring, then X-ray centring
    * If X-ray centring finds a diffracting centre then move to that centre and
    * do a collection with the specified parameters.
    """
    if not oav_params:
        oav_params = OAVParameters(context="xrayCentring")

    flyscan_event_handler = FlyscanEventHandler()

    @subs_decorator(flyscan_event_handler)
    def fetch_results_from_robot_load_then_flyscan():
        yield from robot_load_then_flyscan(composite, params.robot_load_then_centre)

    yield from fetch_results_from_robot_load_then_flyscan()
    assert (
        flyscan_event_handler.flyscan_results
    ), "Flyscan result event not received or no crystal found and exception not raised"

    selection_params = params.select_centres
    selection_func = getattr(flyscan_result, selection_params.name)  # type: ignore
    assert callable(selection_func)
    selection_args = selection_params.model_dump(exclude={"name"})  # type: ignore
    hits: Sequence[flyscan_result.FlyscanResult] = selection_func(
        flyscan_event_handler.flyscan_results, **selection_args
    )  # type: ignore
    LOGGER.info(f"Selected hits {hits} using {selection_func}, args={selection_args}")

    multi_rotation = params.multi_rotation_scan
    rotation_template = multi_rotation.rotation_scans.copy()

    multi_rotation.rotation_scans.clear()

    for hit in hits:
        for rot in rotation_template:
            combination = rot.model_copy()
            combination.x_start_um, combination.y_start_um, combination.z_start_um = (
                axis * 1000 for axis in hit.centre_of_mass_mm
            )
            multi_rotation.rotation_scans.append(combination)

    yield from multi_rotation_scan(composite, multi_rotation, oav_params)
