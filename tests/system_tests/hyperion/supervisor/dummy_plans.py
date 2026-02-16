import asyncio
from unittest.mock import patch

import pydantic
from bluesky import plan_stubs as bps
from bluesky.preprocessors import run_decorator, set_run_key_decorator
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.log import LOGGER as DODAL_LOGGER
from dodal.log import set_up_stream_handler
from ophyd_async.core import (
    observe_value,
    set_mock_value,
)

from mx_bluesky.common.preprocessors.preprocessors import (
    pause_xbpm_feedback_during_collection_at_desired_transmission_decorator,
)
from mx_bluesky.common.utils.exceptions import WarningError
from mx_bluesky.hyperion.blueapi.parameters import LoadCentreCollectParams
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)


def publish_event(plan_name: str):
    yield from bps.open_run(md={"plan_name": plan_name})
    yield from bps.close_run()


def load_centre_collect(
    parameters: LoadCentreCollectParams,
    composite: LoadCentreCollectComposite = inject(),
) -> MsgGenerator:
    yield from bps.sleep(1)


def clean_up_udc(
    visit: str,
    cleanup_group: str = "cleanup",
    robot: BartRobot = inject("robot"),
    smargon: Smargon = inject("gonio"),
    aperture_scatterguard: ApertureScatterguard = inject("aperture_scatterguard"),
    lower_gonio: XYZStage = inject("lower_gonio"),
    detector_motion: DetectorMotion = inject("detector_motion"),
) -> MsgGenerator:
    yield from publish_event("clean_up_udc")
    match visit:
        case "raise_warning_error":
            raise WarningError("Test warning error")
        case "raise_other_error":
            raise RuntimeError("Test unexpected error")
        case "wait_for_abort":
            while True:
                yield from bps.sleep(1)


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class WaitForFeedbackComposite:
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator


def wait_for_feedback(
    devices: WaitForFeedbackComposite = inject(),
) -> MsgGenerator:
    LOGGER.info("wait_for_feedback plan called...")
    set_mock_value(devices.xbpm_feedback.baton_ref().commissioning, False)  # type: ignore
    set_mock_value(devices.xbpm_feedback.pos_stable, 0)

    async def become_stable():
        await asyncio.sleep(2)
        set_mock_value(devices.xbpm_feedback.pos_stable, 1)

    real_observe = observe_value

    async def patched_observe(signal):
        wait_for_stable = asyncio.create_task(become_stable())
        async for _ in real_observe(signal):
            yield _
        await wait_for_stable

    @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
        devices=devices, desired_transmission_fraction=1.0
    )
    @set_run_key_decorator("wait_for_feedback")
    @run_decorator()
    def inner_plan() -> MsgGenerator:
        LOGGER.info("Inner plan called...")
        yield from bps.sleep(5)
        LOGGER.info("Finished waiting")

    with patch(
        "dodal.devices.xbpm_feedback.observe_value", side_effect=patched_observe
    ):
        yield from inner_plan()


set_up_stream_handler(DODAL_LOGGER)
