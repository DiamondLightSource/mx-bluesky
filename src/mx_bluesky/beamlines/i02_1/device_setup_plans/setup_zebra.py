import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import Zebra

ZEBRA_STATUS_TIMEOUT = 30


# Control Eiger from motion controller. Fast shutter is configured in GDA
def setup_zebra_for_xrc_flyscan(
    zebra: Zebra,
    ttl_detector: int | None = None,
    group="setup_zebra_for_xrc",
    wait=True,
):
    """
    Assumes that the motion controller, as part of its gridscan PLC, will send triggers as required to the zebra's
    IN1_TTL to control the detector. The fast shutter is configured in GDA, don't need to touch it in Bluesky for now.
    """
    ttl_detector = ttl_detector or zebra.mapping.outputs.TTL_EIGER
    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.IN1_TTL,
    )
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def tidy_up_zebra_after_gridscan(
    zebra: Zebra,
    ttl_detector: int | None = None,
    group="tidy_up_vmxm_zebra_after_gridscan",
    wait=False,
):
    ttl_detector = ttl_detector or zebra.mapping.outputs.TTL_EIGER

    """# Revert zebra to state expected by GDA"""
    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.OR1,
        group=group,
    )

    if wait:
        yield from bps.wait(group)
