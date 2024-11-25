import json
from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)


class SerialExperiment(BaseModel):
    """Generic parameters common to all serial experiments."""

    visit: Path
    directory: str
    filename: str
    exposure_time_s: float
    detector_distance_mm: float
    detector_name: Literal["eiger", "pilatus"]
    transmission: float

    @field_validator("visit", mode="before")
    @classmethod
    def _parse_visit(cls, visit: str | Path):
        if isinstance(visit, str):
            return Path(visit)
        return visit

    @property
    def collection_directory(self) -> Path:
        return Path(self.visit) / self.directory


class LaserExperiment(BaseModel):
    """Laser settings for pump probe serial collections."""

    laser_dwell_s: float = 0.0  # pump exposure time
    laser_delay_s: float = 0.0  # pump delay
    pre_pump_exposure_s: float | None = None  # Pre illumination, just for chip


class SerialAndLaserExperiment(SerialExperiment, LaserExperiment):
    @classmethod
    def from_file(cls, filename: str | Path):
        with open(filename) as fh:
            raw_params = json.load(fh)
        return cls(**raw_params)

    @property
    @abstractmethod
    def experiment_type(self) -> str:
        pass


class ExtruderParameters(SerialAndLaserExperiment):
    """Extruder parameter model."""

    num_images: int
    pump_status: bool

    @property
    def experiment_type(self) -> str:
        return "extruder"


class ChipDescription(BaseModel):
    """Parameters defining the chip in use for FT collection."""

    chip_type: ChipType
    x_num_steps: int
    y_num_steps: int
    x_step_size: float
    y_step_size: float
    x_blocks: int
    y_blocks: int
    b2b_horz: float
    b2b_vert: float

    @property
    def chip_format(self) -> list[int]:
        return [self.x_blocks, self.y_blocks, self.x_num_steps, self.y_num_steps]

    @property
    def x_block_size(self) -> float:
        if self.chip_type.name == "Custom":
            return 0.0  # placeholder
        else:
            return ((self.x_num_steps - 1) * self.x_step_size) + self.b2b_horz

    @property
    def y_block_size(self) -> float:
        if self.chip_type.name == "Custom":
            return 0.0  # placeholder
        else:
            return ((self.y_num_steps - 1) * self.y_step_size) + self.b2b_vert


class FixedTargetParameters(SerialAndLaserExperiment):
    """Fixed target parameter model."""

    num_exposures: int
    chip: ChipDescription
    map_type: MappingType
    pump_repeat: PumpProbeSetting
    checker_pattern: bool = False
    total_num_images: int = 0  # Calculated in the code for now

    @property
    def experiment_type(self) -> str:
        return "fixed-target"


class BeamSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    wavelength_in_a: float
    beam_size_in_um: Sequence[float]
    beam_center_in_mm: Sequence[float]
