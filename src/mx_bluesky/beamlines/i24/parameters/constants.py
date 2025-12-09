from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class PlanNameConstants:
    ROTATION_DEVICE_READ = "ROTATION DEVICE READ"
    SINGLE_ROTATION_SCAN = "OUTER SINGLE ROTATION SCAN"
    MULTI_ROTATION_SCAN = "OUTER MULTI ROTATION SCAN"
    ROTATION_MAIN = "ROTATION MAIN"
