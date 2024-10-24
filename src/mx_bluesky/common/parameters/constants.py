import os

from pydantic.dataclasses import dataclass

TEST_MODE = os.environ.get("HYPERION_TEST_MODE")  # Environment name will be updated in
# https://github.com/DiamondLightSource/mx-bluesky/issues/214


@dataclass(frozen=True)
class DocDescriptorNames:
    # Robot load event descriptor
    ROBOT_LOAD = "robot_load"
    # For callbacks to use
    OAV_ROTATION_SNAPSHOT_TRIGGERED = "rotation_snapshot_triggered"
    OAV_GRID_SNAPSHOT_TRIGGERED = "snapshot_to_ispyb"
    HARDWARE_READ_PRE = "read_hardware_for_callbacks_pre_collection"
    HARDWARE_READ_DURING = "read_hardware_for_callbacks_during_collection"
    ZOCALO_HW_READ = "zocalo_read_hardware_plan"


@dataclass(frozen=True)
class PlanNameConstants:
    DO_FGS = "do_fgs"


@dataclass(frozen=True)
class TriggerConstants:
    ZOCALO = "trigger_zocalo_on"


@dataclass(frozen=True)
class MxConstants:
    DESCRIPTORS = DocDescriptorNames()
    TRIGGER = TriggerConstants()
    ZOCALO_ENV = "dev_artemis" if TEST_MODE else "artemis"
