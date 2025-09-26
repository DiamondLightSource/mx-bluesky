from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class PlanNameConstants:
    ROTATION_META_READ = "ROTATION_META_READ"
