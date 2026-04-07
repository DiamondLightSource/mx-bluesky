from bluesky import plan_stubs as bps
from bluesky.preprocessors import run_decorator, set_run_key_decorator, subs_decorator
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector
from dodal.devices.smargon import CombinedMove

from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.common.utils.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.blueapi.mixins import MultiXtalSelection
from mx_bluesky.hyperion.experiment_plans.pin_centre_then_gridscan_plan import (
    pin_centre_then_gridscan_plan,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import PinTipCentreThenXrayCentre
from mx_bluesky.hyperion.utils.centre_selection import samples_and_locations_to_collect


def pin_tip_centre_then_xray_centre(
    composite: HyperionGridDetectThenXRayCentreComposite,
    parameters: PinTipCentreThenXrayCentre,
    centre_selection: MultiXtalSelection,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    Performs pin-tip centring of the currently loaded sample,
    followed by x-ray gridscan and centring on the best sample.
    Args:
        composite (HyperionGridDetectThenXRayCentreComposite): devices to use
        parameters (PinTipCentreThenXrayCentre): centring parameters
        centre_selection (MultiXtalSelection): The selection algorithm to determine the centres to select from the XRC results
        oav_config_file (str): Optional OAV configuration file
    Raises:
        CrystalNotFoundError: If no centres were found if commissioning mode was not selected.
    """
    eiger: EigerDetector = composite.eiger

    eiger.set_detector_parameters(parameters.detector_params)

    xrc_event_handler = XRayCentreEventHandler()

    @subs_decorator(xrc_event_handler)
    @set_run_key_decorator(CONST.PLAN.PIN_TIP_CENTRE_THEN_XRC)
    @run_decorator(
        md={
            "metadata": {
                "sample_id": parameters.sample_id,
                "visit": parameters.visit,
                "container": parameters.sample_puck,
            },
            "activate_callbacks": [
                "BeamDrawingCallback",
            ],
        }
    )
    def pin_centre_flyscan_then_fetch_results() -> MsgGenerator:
        yield from pin_centre_then_gridscan_plan(composite, parameters, oav_config_file)

        results = xrc_event_handler.xray_centre_results
        sample_ids_and_locations = yield from samples_and_locations_to_collect(
            centre_selection, composite.gonio, parameters.sample_id, results
        )

        if sample_ids_and_locations:
            location = [pos_um / 1000 for pos_um in sample_ids_and_locations[0][1]]
            yield from bps.abs_set(
                composite.gonio,
                CombinedMove(x=location[0], y=location[1], z=location[2]),
                wait=True,
            )

    yield from pin_centre_flyscan_then_fetch_results()
