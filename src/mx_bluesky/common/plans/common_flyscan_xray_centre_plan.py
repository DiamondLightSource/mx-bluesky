from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

import pydantic
from bluesky.utils import MsgGenerator
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
    ZebraFastGridScan,
)
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanEssentialDevices:
    attenuator: EnumFilterAttenuator
    backlight: Backlight
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    synchrotron: Synchrotron
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    smargon: Smargon


D = TypeVar(name="D", bound="FlyScanEssentialDevices")


@dataclasses.dataclass
class _FeatureControlled(Generic[D]):
    class _ZebraSetup(Protocol):
        def __call__(
            self, zebra: Zebra, group="setup_zebra_for_gridscan", wait=True
        ) -> MsgGenerator: ...

    class _ExtraSetup(Protocol):
        def __call__(
            self,
            fgs_composite: D,
            parameters: type[SpecifiedThreeDGridScan],
        ) -> MsgGenerator: ...

    setup_trigger: _ExtraSetup
    tidy_plan: Callable[[D], MsgGenerator]
    set_flyscan_params: Callable[[], MsgGenerator]
    fgs_motors: FastGridScanCommon
