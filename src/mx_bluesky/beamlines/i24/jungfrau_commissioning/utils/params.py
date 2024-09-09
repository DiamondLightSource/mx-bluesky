import json

from dodal.devices.zebra import RotationDirection
from pydantic import BaseModel


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

    @classmethod
    def from_file(cls, filename: str):
        with open(filename) as f:
            raw = json.load(f)
        return cls(**raw)

    def print(self):
        print(self.model_dump_json(indent=2))

    def get_num_images(self):
        return int(self.scan_width_deg / self.image_width_deg)
