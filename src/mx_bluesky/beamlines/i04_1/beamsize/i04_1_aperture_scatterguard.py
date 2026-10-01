from asyncio import Event
from collections.abc import Sequence
from typing import Protocol, TypeAlias, runtime_checkable

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import BeamSizePlans
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.event_mapping import (
    BeamSizePayload,
)
from mx_bluesky.common.parameters.components import AperturePolicy

I04_1_ApSgValue: TypeAlias = None


@runtime_checkable
class I04_1_ApertureScatterguardComposite(Protocol):  # noqa: N801
    # TODO insert new aperture device here
    ...


class I04_1_BeamSizePlans(  # noqa: N801
    BeamSizePlans[I04_1_ApertureScatterguardComposite, I04_1_ApSgValue]
):
    def make_safe_for_robot_load_plan(
        self, devices: I04_1_ApertureScatterguardComposite, group: str
    ) -> MsgGenerator:
        """Nothing to do for this."""
        yield from bps.null()

    def make_safe_for_oav(
        self, devices: I04_1_ApertureScatterguardComposite, group: str
    ) -> MsgGenerator:
        """Nothing to do for this."""
        yield from bps.null()

    def prepare_beam_size(
        self,
        devices: I04_1_ApertureScatterguardComposite,
        aperture_value: I04_1_ApSgValue,
        group: str,
    ) -> MsgGenerator:
        """Beam size is never changed"""
        yield from bps.null()

    def perform_beam_size(
        self,
        devices: I04_1_ApertureScatterguardComposite,
        aperture_value: I04_1_ApSgValue,
        group: str,
    ) -> MsgGenerator:
        """Beam size is never changed"""
        yield from bps.null()

    def beam_size_for_xrc(
        self,
        devices: I04_1_ApertureScatterguardComposite,
        aperture_policy: AperturePolicy,
    ) -> MsgGenerator[I04_1_ApSgValue]:
        """Beam size is never changed"""
        yield from bps.null()
        return None

    def beam_size_for_rotation(
        self,
        devices: I04_1_ApertureScatterguardComposite,
        aperture_policy: AperturePolicy,
    ) -> MsgGenerator[I04_1_ApSgValue]:
        """Beam size is never changed"""
        yield from bps.null()
        return None

    def signals_to_read_during_collection(
        self, devices: I04_1_ApertureScatterguardComposite
    ) -> Sequence:
        # TODO obtain deposition beam size from aperture setting
        return []


def map_hw_read_during_data(doc: Event) -> BeamSizePayload:
    # TODO - read signals for current aperture setting
    return BeamSizePayload()
