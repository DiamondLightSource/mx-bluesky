from typing import Protocol, TypeAlias

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from typing_extensions import runtime_checkable

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import BeamSizePlans
from mx_bluesky.common.parameters.components import AperturePolicy
from mx_bluesky.common.utils.log import LOGGER

ApertureScatterguardValue: TypeAlias = ApertureValue | None


@runtime_checkable
class ApertureScatterguardComposite(Protocol):
    aperture_scatterguard: ApertureScatterguard


class Phase1ApertureScatterguardPlans(
    BeamSizePlans[ApertureScatterguardComposite, ApertureScatterguardValue]
):
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

    def prepare_beam_size(
        self,
        devices: ApertureScatterguardComposite,
        aperture_value: ApertureScatterguardValue,
        group: str,
    ) -> MsgGenerator:
        if aperture_value:
            yield from bps.prepare(
                devices.aperture_scatterguard,
                aperture_value,
                group=group,
            )

    def perform_beam_size(
        self,
        devices: ApertureScatterguardComposite,
        aperture_value: ApertureScatterguardValue,
        group: str,
    ) -> MsgGenerator:
        if aperture_value:
            LOGGER.info(f"Setting aperture position to {aperture_value}")

            yield from bps.abs_set(
                devices.aperture_scatterguard.selected_aperture,
                aperture_value,
                group=group,
            )
        else:
            previous_aperture_position = yield from bps.rd(
                devices.aperture_scatterguard
            )
            assert isinstance(previous_aperture_position, ApertureValue)
            LOGGER.info(
                f"Using previously set aperture position {previous_aperture_position}"
            )

    def beam_size_for_rotation(
        self,
        devices: ApertureScatterguardComposite,
        aperture_policy: AperturePolicy,
    ) -> MsgGenerator[ApertureScatterguardValue]:
        yield from iter([])
        match aperture_policy:
            case AperturePolicy.SMALL:
                return ApertureValue.SMALL
            case AperturePolicy.MEDIUM:
                return ApertureValue.MEDIUM
            case AperturePolicy.LARGE | AperturePolicy.AUTO:
                return ApertureValue.LARGE
            case AperturePolicy.CURRENT_POSITION:
                return None
            case _:
                raise ValueError(f"Unsupported aperture policy {aperture_policy}")

    def beam_size_for_xrc(
        self, devices: ApertureScatterguardComposite, aperture_policy: AperturePolicy
    ) -> MsgGenerator[ApertureScatterguardValue]:
        match aperture_policy:
            case AperturePolicy.SMALL | AperturePolicy.AUTO:
                return ApertureValue.SMALL
            case AperturePolicy.MEDIUM:
                return ApertureValue.MEDIUM
            case AperturePolicy.LARGE:
                return ApertureValue.LARGE
            case AperturePolicy.CURRENT_POSITION:
                previous_aperture_position = yield from bps.rd(
                    devices.aperture_scatterguard
                )
                assert isinstance(previous_aperture_position, ApertureValue)
                LOGGER.info(
                    f"Using previously set aperture position {previous_aperture_position}"
                )
                return previous_aperture_position
            case _:
                raise ValueError(f"Unsupported aperture policy {aperture_policy}")
