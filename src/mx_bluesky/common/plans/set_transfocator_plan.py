from bluesky import plan_stubs as bps
from dodal.beamlines.i04 import transfocator


def test_transfocator(beamsize_mirons):
    device = transfocator()
    # Sensible beamsize?
    yield from bps.abs_set(device, beamsize_mirons, group="SetTransfocator", wait=False)
    print("Transfocator is being set...")
    yield from bps.wait(group="SetTransfocator")
    print("Done!")


if __name__ == "__main__":
    print("Running test_tranfocator plan")
    test_transfocator(315)
