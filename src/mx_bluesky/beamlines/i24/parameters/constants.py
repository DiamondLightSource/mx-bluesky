from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class PlanNameConstants:
    ROTATION_META_READ = "ROTATION_META_READ"
    SINGLE_ROTATION_SCAN = "OUTER SINGLE ROTATION SCAN"
    MULTI_ROTATION_SCAN = "OUTER MULTI ROTATION SCAN"
