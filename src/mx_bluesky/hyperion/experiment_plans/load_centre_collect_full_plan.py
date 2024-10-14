import dataclasses

from blueapi.core import BlueskyContext
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
    multi_rotation_scan,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.utils.context import device_composite_from_context


@dataclasses.dataclass
class LoadCentreCollectComposite(RobotLoadThenCentreComposite, RotationScanComposite):
    """Composite that provides access to the required devices."""

    pass


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
    yield from robot_load_then_centre(composite, params.robot_load_then_centre)

    yield from multi_rotation_scan(composite, params.multi_rotation_scan, oav_params)
