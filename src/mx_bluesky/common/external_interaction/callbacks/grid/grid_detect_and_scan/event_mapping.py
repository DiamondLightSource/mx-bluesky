from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeAlias

from event_model import Event


@dataclass
class DetectorPayload:
    bit_depth: int
    ispyb_detector_id: int
    roi_mode: bool


@dataclass
class BeamSizePayload:
    aperture: str = "Not implemented"
    beamsize_x_um: float | None = None
    beamsize_y_um: float | None = None


@dataclass
class HWReadDuringPayload:
    detector_payload: DetectorPayload
    beamsize_payload: BeamSizePayload = field(default_factory=BeamSizePayload)


HWReadDuringMapper: TypeAlias = Callable[[Event], HWReadDuringPayload]
