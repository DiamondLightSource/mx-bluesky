import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import (
    ArmDemand,
    Zebra,
)
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
)

from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    configure_zebra_and_shutter_for_auto_shutter,
)
from mx_bluesky.common.parameters.constants import ZEBRA_STATUS_TIMEOUT


def arm_zebra(zebra: Zebra):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.ARM, wait=True)


def setup_zebra_for_panda_flyscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="setup_zebra_for_panda_flyscan",
    wait=True,
):
    # Forwards eiger trigger signal from panda
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR],
        zebra.mapping.sources.IN1_TTL,
        group=group,
    )

    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, zebra_shutter, zebra.mapping.sources.IN4_TTL, group=group
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_XSPRESS3],
        zebra.mapping.sources.DISCONNECT,
        group=group,
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_PANDA],
        zebra.mapping.sources.IN3_TTL,
        group=group,
    )  # Tells panda that motion is beginning/changing direction

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
