from typing import Protocol

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from typing_extensions import runtime_checkable

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import BeamSizePlans


@runtime_checkable
class ApertureScatterguardComposite(Protocol):
    aperture_scatterguard: ApertureScatterguard


class Phase1ApertureScatterguardPlans(BeamSizePlans[ApertureScatterguardComposite]):
    def make_safe_for_robot_load_plan(
        self, devices: ApertureScatterguardComposite, group: str
    ) -> MsgGenerator:
        yield from bps.abs_set(
            devices.aperture_scatterguard.selected_aperture,
            ApertureValue.OUT_OF_BEAM,
            group=group,
        )

    def make_safe_for_oav(
        self, devices: ApertureScatterguardComposite, group: str
    ) -> MsgGenerator:
        yield from bps.abs_set(
            devices.aperture_scatterguard.selected_aperture,
            ApertureValue.OUT_OF_BEAM,
            group=group,
        )
