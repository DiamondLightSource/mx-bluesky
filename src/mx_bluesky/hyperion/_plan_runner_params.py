"""Internal parameter models for the private use of hyperion plan runners only."""

from pydantic import BaseModel


class Wait(BaseModel):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float


class UDCDefaultState(BaseModel):
    """Represents an instruction to execute the UDC default state plan."""

    pass


class UDCCleanup(BaseModel):
    """Represents an instruction to perform UDC Cleanup,
    in which the detector shutter is closed and a robot unload is performed."""

    pass
