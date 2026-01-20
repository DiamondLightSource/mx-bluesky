from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon

from mx_bluesky.common.utils.exceptions import WarningError
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


def publish_event(plan_name: str):
    yield from bps.open_run(md={"plan_name": plan_name})
    yield from bps.close_run()


def load_centre_collect(
    parameters: LoadCentreCollect,
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
