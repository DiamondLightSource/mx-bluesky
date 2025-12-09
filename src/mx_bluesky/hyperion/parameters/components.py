from mx_bluesky.common.parameters.components import MxBlueskyParameters


class Wait(MxBlueskyParameters):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float


class UDCDefaultState(MxBlueskyParameters):
    """Represents an instruction to execute the UDC default state plan."""

    pass


class UDCCleanup(MxBlueskyParameters):
    """Represents an instruction to perform UDC Cleanup,
    in which the detector shutter is closed and a robot unload is performed."""

    pass
