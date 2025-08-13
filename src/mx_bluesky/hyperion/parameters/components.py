from mx_bluesky.common.parameters.components import MxBlueskyParameters


class Wait(MxBlueskyParameters):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float
