import json
from typing import Any

from dodal.devices.motors import XYZLimitBundle
from dodal.devices.zebra import RotationDirection
from pydantic import BaseModel, validator


class RotationScanParameters(BaseModel):
    """
    Holder class for the parameters of a rotation data collection.
    """

    rotation_axis: str = "omega"
    scan_width_deg: float = 360.0
    image_width_deg: float = 0.1
    omega_start_deg: float = 0.0
    exposure_time_s: float = 0.01
    acquire_time_s: float = 10.0
    offset_deg: float = 10.0
    x: float | None = None
    y: float | None = None
    z: float | None = None
    rotation_direction: RotationDirection = RotationDirection.NEGATIVE
    shutter_opening_time_s: float = 0.6
    storage_directory: str = "/tmp/jungfrau_data/"
    nexus_filename: str = "scan"

    class Config:
        json_encoders = {
            RotationDirection: lambda x: x.name,
        }

    @validator("rotation_direction", pre=True)
    def _parse_direction(cls, rotation_direction: str | int):
        if isinstance(rotation_direction, str):
            return RotationDirection[rotation_direction]
        else:
            return RotationDirection(rotation_direction)

    @validator("acquire_time_s", pre=True)
    def _validate_acquision(cls, acquire_time_s: float, values: dict[str, Any]):
        if acquire_time_s < values["exposure_time_s"]:
            raise ValueError("Acquisition time must not be shorter than exposure time!")
        return acquire_time_s

    @classmethod
    def from_file(cls, filename: str):
        with open(filename) as f:
            raw = json.load(f)
        return cls(**raw)

    def print(self):
        print(self.json(indent=2))

    def xyz_are_valid(self, limits: XYZLimitBundle) -> bool:
        """
        Validates scan location in x, y, and z

        :param limits: The motor limits against which to validate
                       the parameters
        :return: True if the scan is valid
        """
        if not limits.x.is_within(self.x):
            return False
        if not limits.y.is_within(self.y):
            return False
        if not limits.z.is_within(self.z):
            return False
        return True

    def get_num_images(self):
        return int(self.scan_width_deg / self.image_width_deg)
