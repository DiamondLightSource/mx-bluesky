from __future__ import annotations

from collections.abc import Sequence

import pydantic
from blueapi.core import BlueskyContext
from bluesky.preprocessors import run_decorator, set_run_key_decorator, subs_wrapper
from bluesky.utils import MsgGenerator
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon

import mx_bluesky.hyperion.experiment_plans.common.xrc_result as flyscan_result
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    XRayCentreEventHandler,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    MultiRotationScan,
    RotationScanComposite,
    multi_rotation_scan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    sample_handling_callback_decorator,
)
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.utils.context import device_composite_from_context


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class LoadCentreCollectComposite(RobotLoadThenCentreComposite, RotationScanComposite):
    """Composite that provides access to the required devices."""

    @property
    def sample_motors(self) -> Smargon:
        return self.smargon


def create_devices(context: BlueskyContext) -> LoadCentreCollectComposite:
    """Create the necessary devices for the plan."""
    return device_composite_from_context(context, LoadCentreCollectComposite)


def load_centre_collect_full(
    composite: LoadCentreCollectComposite,
    parameters: LoadCentreCollect,
    oav_params: OAVParameters | None = None,
) -> MsgGenerator:
    """Attempt a complete data collection experiment, consisting of the following:
    * Load the sample if necessary
    * Move to the specified goniometer start angles
    * Perform optical centring, then X-ray centring
    * If X-ray centring finds a diffracting centre then move to that centre and
    * do a collection with the specified parameters.
    """
    if not oav_params:
        oav_params = OAVParameters(context="xrayCentring")

    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "metadata": {"sample_id": parameters.sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    @sample_handling_callback_decorator()
    def plan_with_callback_subs():
        flyscan_event_handler = XRayCentreEventHandler()
        yield from subs_wrapper(
            robot_load_then_xray_centre(composite, parameters.robot_load_then_centre),
            flyscan_event_handler,
        )

        assert flyscan_event_handler.xray_centre_results, "Flyscan result event not received or no crystal found and exception not raised"

        selection_func = flyscan_result.resolve_selection_fn(
            parameters.selection_params
        )
        hits: Sequence[flyscan_result.XRayCentreResult] = selection_func(
            flyscan_event_handler.xray_centre_results
        )
        LOGGER.info(
            f"Selected hits {hits} using {selection_func}, args={parameters.selection_params}"
        )

        multi_rotation = parameters.multi_rotation_scan
        rotation_template = multi_rotation.rotation_scans.copy()

        multi_rotation.rotation_scans.clear()

        for hit in hits:
            for rot in rotation_template:
                combination = rot.model_copy()
                (
                    combination.x_start_um,
                    combination.y_start_um,
                    combination.z_start_um,
                ) = (axis * 1000 for axis in hit.centre_of_mass_mm)
                multi_rotation.rotation_scans.append(combination)
        multi_rotation = MultiRotationScan.model_validate(multi_rotation)

        assert (
            multi_rotation.demand_energy_ev
            == parameters.robot_load_then_centre.demand_energy_ev
        ), "Setting a different energy for gridscan and rotation is not supported"
        yield from multi_rotation_scan(composite, multi_rotation, oav_params)

    yield from plan_with_callback_subs()
