import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import Zebra

ZEBRA_STATUS_TIMEOUT = 30


# TODO: Check this with Andy - current deployed code sets TTL 4
def setup_zebra_for_xrc_flyscan(zebra: Zebra, group="setup_zebra_for_xrc", wait=True):
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_EIGER],
        zebra.mapping.sources.IN1_TTL,
    )
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def tidy_up_zebra_after_gridscan(
    zebra: Zebra, group="tidyup_vmxm_zebra_after_gridscan", wait=False
):
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_EIGER],
        zebra.mapping.sources.OR1,
        group=group,
    )

    if wait:
        yield from bps.wait(group)
