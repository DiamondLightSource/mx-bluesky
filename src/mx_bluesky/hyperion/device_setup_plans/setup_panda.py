from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import cast

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_utils import get_path_provider
from dodal.common.types import UpdatingPathProvider
from dodal.devices.fast_grid_scan import PandAGridScanParams
from dodal.devices.smargon import Smargon
from ophyd_async.fastcs.panda import (
    HDFPanda,
    SeqTable,
    SeqTrigger,
)

from mx_bluesky.common.device_setup_plans.setup_panda import load_panda_from_yaml
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import DeviceSettingsConstants

MM_TO_ENCODER_COUNTS = 200000
GENERAL_TIMEOUT = 60
TICKS_PER_MS = 1000  # Panda sequencer prescaler will be set to us
PULSE_WIDTH_US = 50


class Enabled(Enum):
    ENABLED = "ONE"
    DISABLED = "ZERO"


class PcapArm(Enum):
    ARMED = "Arm"
    DISARMED = "Disarm"


def _get_seq_table(
    parameters: PandAGridScanParams, exposure_distance_mm, time_between_steps_ms
) -> SeqTable:
    """
    Generate the sequencer table for the panda.

    - Sending a 'trigger' means trigger PCAP internally and send signal to Eiger via physical panda output

    SEQUENCER TABLE:

        1. Wait for physical trigger from motion script to mark start of scan / change of direction
        2. Wait for POSA (X2) to be greater than X_START and send x_steps triggers every time_between_steps_ms
        3. Wait for physical trigger from motion script to mark change of direction
        4. Wait for POSA (X2) to be less than X_START + X_STEP_SIZE * x_steps + exposure distance, then
            send x_steps triggers every time_between_steps_ms
        5. Go back to step one.

        For a more detailed explanation and a diagram, see https://github.com/DiamondLightSource/hyperion/wiki/PandA-constant%E2%80%90motion-scanning

        For documentation on Panda itself, see https://pandablocks.github.io/PandABlocks-FPGA/master/index.html

    Args:
        exposure_distance_mm: The distance travelled by the sample each time the detector is exposed: exposure time * sample velocity
        time_between_steps_ms: The time taken to traverse between each grid step.
        parameters: Parameters for the panda gridscan

    Returns:
        An instance of SeqTable describing the panda sequencer table
    """

    start_of_grid_x_counts = int(parameters.x_start_mm * MM_TO_ENCODER_COUNTS)

    # x_start is the first trigger point, so we need to travel to x_steps-1 for the final trigger point
    end_of_grid_x_counts = int(
        start_of_grid_x_counts
        + (parameters.x_step_size_mm * (parameters.x_steps - 1) * MM_TO_ENCODER_COUNTS)
    )

    exposure_distance_x_counts = int(exposure_distance_mm * MM_TO_ENCODER_COUNTS)

    num_pulses = parameters.x_steps

    # Integer precision here is 1e-6s, so casting is safe
    delay_between_pulses = int(time_between_steps_ms * TICKS_PER_MS)

    assert delay_between_pulses > PULSE_WIDTH_US

    # BITA_1 trigger wired from TTLIN1, this is the trigger input

    # +ve direction scan

    table = (
        SeqTable.row(trigger=SeqTrigger.BITA_1, time2=1)
        + SeqTable.row(
            repeats=num_pulses,
            trigger=SeqTrigger.POSA_GT,
            position=start_of_grid_x_counts,
            time1=PULSE_WIDTH_US,
            outa1=True,
            time2=delay_between_pulses - PULSE_WIDTH_US,
            outa2=False,
        )
        +
        # -ve direction scan
        SeqTable.row(trigger=SeqTrigger.BITA_1, time2=1)
        + SeqTable.row(
            repeats=num_pulses,
            trigger=SeqTrigger.POSA_LT,
            position=end_of_grid_x_counts + exposure_distance_x_counts,
            time1=PULSE_WIDTH_US,
            outa1=True,
            time2=delay_between_pulses - PULSE_WIDTH_US,
            outa2=False,
        )
    )

    return table


def setup_panda_for_flyscan(
    panda: HDFPanda,
    parameters: PandAGridScanParams,
    smargon: Smargon,
    exposure_time_s: float,
    time_between_x_steps_ms: float,
    sample_velocity_mm_per_s: float,
) -> MsgGenerator:
    """Configures the PandA device for a flyscan.
    Sets PVs from a yaml file, calibrates the encoder, and
    adjusts the sequencer table based off the grid parameters. Yaml file can be
    created using ophyd_async.core.save_device()

    Args:
        panda (HDFPanda): The PandA Ophyd device
        parameters (PandAGridScanParams): Grid parameters
        smargon (Smargon): The Smargon Ophyd device
        exposure_time_s (float): Detector exposure time per trigger
        time_between_x_steps_ms (float): Time, in ms, between each trigger. Equal to deadtime + exposure time
        sample_velocity_mm_per_s (float): Velocity of the sample in mm/s = x_step_size_mm * 1000 /
            time_between_x_steps_ms
    Returns:
        MsgGenerator

    Yields:
        Iterator[MsgGenerator]
    """
    assert parameters.x_steps > 0
    assert time_between_x_steps_ms * 1000 >= exposure_time_s
    assert sample_velocity_mm_per_s * exposure_time_s < parameters.x_step_size_mm

    yield from bps.stage(panda, group="panda-config")

    yield from load_panda_from_yaml(
        DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_DIR,
        DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_FILENAME,
        panda,
    )

    initial_x = yield from bps.rd(smargon.x.user_readback)
    initial_y = yield from bps.rd(smargon.y.user_readback)
    initial_z = yield from bps.rd(smargon.z.user_readback)

    # Home the PandA X, Y, and Z encoders using current motor position
    yield from bps.abs_set(
        panda.inenc[1].setp,  # type: ignore
        initial_x * MM_TO_ENCODER_COUNTS,
        wait=True,
    )

    yield from bps.abs_set(
        panda.inenc[2].setp,  # type: ignore
        initial_y * MM_TO_ENCODER_COUNTS,
        wait=True,
    )

    yield from bps.abs_set(
        panda.inenc[3].setp,  # type: ignore
        initial_z * MM_TO_ENCODER_COUNTS,
        wait=True,
    )

    yield from bps.abs_set(panda.pulse[1].width, exposure_time_s, group="panda-config")

    exposure_distance_mm = sample_velocity_mm_per_s * exposure_time_s

    table = _get_seq_table(parameters, exposure_distance_mm, time_between_x_steps_ms)

    yield from bps.abs_set(panda.seq[1].table, table, group="panda-config")

    yield from bps.abs_set(
        panda.pcap.enable,  # type: ignore
        Enabled.ENABLED.value,
        group="panda-config",
    )

    # Values need to be set before blocks are enabled, so wait here
    yield from bps.wait(group="panda-config", timeout=GENERAL_TIMEOUT)

    LOGGER.info(f"PandA sequencer table has been set to: {str(table)}")
    table_readback = yield from bps.rd(panda.seq[1].table)
    LOGGER.debug(f"PandA sequencer table readback is: {str(table_readback)}")

    yield from arm_panda_for_gridscan(panda)


def arm_panda_for_gridscan(panda: HDFPanda, group="arm_panda_gridscan"):
    yield from bps.abs_set(panda.seq[1].enable, Enabled.ENABLED.value, group=group)  # type: ignore
    yield from bps.abs_set(panda.pulse[1].enable, Enabled.ENABLED.value, group=group)  # type: ignore
    yield from bps.abs_set(panda.counter[1].enable, Enabled.ENABLED.value, group=group)  # type: ignore
    yield from bps.abs_set(panda.pcap.arm, PcapArm.ARMED.value, group=group)  # type: ignore
    yield from bps.wait(group=group, timeout=GENERAL_TIMEOUT)
    LOGGER.info("PandA has been armed")


def disarm_panda_for_gridscan(panda, group="disarm_panda_gridscan") -> MsgGenerator:
    yield from bps.abs_set(panda.pcap.arm, PcapArm.DISARMED.value, group=group)  # type: ignore
    yield from bps.abs_set(panda.counter[1].enable, Enabled.DISABLED.value, group=group)  # type: ignore
    yield from bps.abs_set(panda.seq[1].enable, Enabled.DISABLED.value, group=group)
    yield from bps.abs_set(panda.pulse[1].enable, Enabled.DISABLED.value, group=group)
    yield from bps.abs_set(panda.pcap.enable, Enabled.DISABLED.value, group=group)  # type: ignore
    yield from bps.wait(group=group, timeout=GENERAL_TIMEOUT)


def set_panda_directory(panda_directory: Path) -> MsgGenerator:
    """Updates the root folder which is used by the PandA's PCAP."""

    suffix = datetime.now().strftime("_%Y%m%d%H%M%S")

    async def set_panda_dir():
        await cast(UpdatingPathProvider, get_path_provider()).update(
            directory=panda_directory, suffix=suffix
        )

    yield from bps.wait_for([set_panda_dir])
