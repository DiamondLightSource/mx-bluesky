import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import Zebra

ZEBRA_STATUS_TIMEOUT = 30


def setup_zebra_for_xrc_flyscan(zebra: Zebra, group="setup_zebra_for_xrc", wait=False):
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.sources.IN4_TTL],
        zebra.mapping.outputs.TTL_DETECTOR,
    )
