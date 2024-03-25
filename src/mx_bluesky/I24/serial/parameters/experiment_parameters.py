from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, validator

from mx_bluesky.I24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)


class SerialExperiment(BaseModel):
    """Generic parameters common to all serial experiments."""

    visit: str
    directory: str
    filename: str
    exposure_time_s: float
    detector_distance_mm: float
    detector_name: Literal["eiger", "pilatus"]


class LaserExperiment(BaseModel):
    """Laser settings for pump probe serial collections."""

    laser_dwell_s: Optional[float] = None  # pump exposure time
    laser_delay_s: Optional[float] = None  # pump delay
    pre_pump_exposure_s: Optional[float] = None  # Pre illumination, just for chip


class ExtruderParameters(SerialExperiment, LaserExperiment):
    """Extruder parameter model."""

    num_images: int
    pump_status: bool

    @classmethod
    def from_file(cls, filename: str | Path):
        with open(filename, "r") as fh:
            raw_params = json.load(fh)
        return cls(**raw_params)


class FixedTargetParameters(SerialExperiment, LaserExperiment):
    """Fixed target parameter model."""

    model_config = ConfigDict(use_enum_values=True)

    num_exposures: int
    chip_type: ChipType
    map_type: MappingType
    pump_repeat: PumpProbeSetting
    checker_pattern: bool = False

    @validator("chip_type", pre=True)
    def _parse_chip(cls, chip_type: str | int):
        if isinstance(chip_type, str):
            return ChipType[chip_type]
        else:
            return ChipType(chip_type)

    @validator("map_type", pre=True)
    def _parse_map(cls, map_type: str | int):
        if isinstance(map_type, str):
            return MappingType[map_type]
        else:
            return MappingType(map_type)

    @classmethod
    def from_file(cls, filename: str | Path):
        with open(filename, "r") as fh:
            raw_params = json.load(fh)
        return cls(**raw_params)

    def get_approx_chip_size(self) -> float:
        """Returns an approximation of the chip size for the move during alignment \
            of the fiducials
        """
        if str(self.chip_type) == "OxfordInner":
            return 24.60
        else:
            return 25.40
