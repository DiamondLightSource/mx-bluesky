from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from event_model import Event


@dataclass
class HWReadDuringPayload:
    bit_depth: int
    ispyb_detector_id: int
    roi_mode: bool


HWReadDuringMapper: TypeAlias = Callable[[Event], HWReadDuringPayload]
