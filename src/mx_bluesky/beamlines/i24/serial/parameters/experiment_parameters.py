import json
from abc import abstractmethod
from pathlib import Path

import numpy as np
from dodal.devices.detector.det_dim_constants import (
    EIGER2_X_9M_SIZE,
    PILATUS_6M_SIZE,
    DetectorSizeConstants,
)
from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    DetectorName,
    SSXType,
)


class SerialExperiment(BaseModel):
    """Generic parameters common to all serial experiments."""

    visit: Path
    directory: str
    filename: str
    exposure_time_s: float
    detector_distance_mm: float
    detector_name: DetectorName
    transmission: float

    @field_validator("visit", mode="before")
    @classmethod
    def _parse_visit(cls, visit: str | Path):
        if isinstance(visit, str):
            return Path(visit)
        return visit

    @property
    def collection_directory(self) -> Path:
        directory = Path(self.visit) / self.directory
        return directory

    @property
    def detector_size_constants(self) -> DetectorSizeConstants:
        return (
            EIGER2_X_9M_SIZE
            if self.detector_name is DetectorName.EIGER
            else PILATUS_6M_SIZE
        )


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
    def nexgen_experiment_type(self) -> str:
        pass

    @property
    @abstractmethod
    def ispyb_experiment_type(self) -> SSXType:
        pass


class ExtruderParameters(SerialAndLaserExperiment):
    """Extruder parameter model."""

    num_images: int
    pump_status: bool

    @property
    def nexgen_experiment_type(self) -> str:
        return "extruder"

    @property
    def ispyb_experiment_type(self) -> SSXType:
        return SSXType.EXTRUDER


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

    @property
    def tot_num_blocks(self) -> int:
        return self.x_blocks * self.y_blocks


class FixedTargetParameters(SerialAndLaserExperiment):
    """Fixed target parameter model."""

    num_exposures: int
    chip: ChipDescription
    map_type: MappingType
    pump_repeat: PumpProbeSetting
    checker_pattern: bool = False
    chip_map: list[int]

    @property
    def nexgen_experiment_type(self) -> str:
        return "fixed-target"

    @property
    def ispyb_experiment_type(self) -> SSXType:
        return SSXType.FIXED

    @computed_field  # type: ignore   # Mypy doesn't like it
    @property
    def total_num_images(self) -> int:
        match self.map_type:
            case MappingType.NoMap:
                if self.chip.chip_type is ChipType.Custom:
                    num_images = (
                        self.chip.x_num_steps
                        * self.chip.y_num_steps
                        * self.num_exposures
                    )
                else:
                    chip_format = self.chip.chip_format[:4]
                    num_images = int(np.prod(chip_format) * self.num_exposures)
            case MappingType.Lite:
                chip_format = self.chip.chip_format[2:4]
                block_count = len(self.chip_map)  # type: ignore
                num_images = int(
                    np.prod(chip_format) * block_count * self.num_exposures
                )
        return num_images


class BeamSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    wavelength_in_a: float
    beam_size_in_um: tuple[float, float]
    beam_center_in_mm: tuple[float, float]
