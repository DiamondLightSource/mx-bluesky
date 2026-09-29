from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import TypeAlias

from event_model import Event


@dataclass
class DetectorPayload:
    bit_depth: int
    ispyb_detector_id: int
    roi_mode: bool


@dataclass
class BeamSizePayload:
    aperture: str


@dataclass
class HWReadDuringPayload:
    detector_payload: DetectorPayload
    beamsize_payload: BeamSizePayload = field(
        default_factory=partial(BeamSizePayload, aperture="Not implemented")
    )


HWReadDuringMapper: TypeAlias = Callable[[Event], HWReadDuringPayload]
