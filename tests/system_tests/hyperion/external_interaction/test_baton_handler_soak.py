import os
from dataclasses import fields
from time import sleep
from unittest.mock import patch
from weakref import WeakValueDictionary

import pytest
from bluesky import RunEngine
from ophyd_async.core import Device
from ophyd_async.plan_stubs import ensure_connected

from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.hyperion.baton_handler import initialise_udc
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.utils.context import setup_context

weak_ids_to_devices = WeakValueDictionary()


MAX_DEVICE_COUNT = 20

STOP_ON_LEAK_DETECTION = True


@pytest.mark.parametrize("i", list(range(1, 101)))
@patch.dict(os.environ, {"BEAMLINE": "i03"})
def test_udc_reloads_all_devices_soak_test_dev_mode(RE: RunEngine, i: int):
    reinitialise_beamline(True, i)


@pytest.fixture
def patch_ensure_connected():
    unpatched = ensure_connected

    def patched_func(*devices: Device, mock=False, timeout=1, force_reconnect=False):
        timeout = 1
        yield from unpatched(
            *devices, mock=mock, timeout=timeout, force_reconnect=force_reconnect
        )

    with patch(
        "blueapi.utils.connect_devices.ensure_connected", side_effect=patched_func
    ) as p:
        yield p


@pytest.mark.parametrize("i", list(range(1, 101)))
@patch.dict(os.environ, {"BEAMLINE": "i03"})
@patch("ophyd_async.plan_stubs._ensure_connected.DEFAULT_TIMEOUT", 1)
@pytest.mark.timeout(1e6)
def test_udc_reloads_all_devices_soak_test_real(
    RE: RunEngine, i: int, patch_ensure_connected
):
    reinitialise_beamline(False, i)


def reinitialise_beamline(dev_mode: bool, i: int):
    dev_mode: bool
    context = setup_context(dev_mode)
    devices_before_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )
    for f in fields(devices_before_reset):
        device = getattr(devices_before_reset, f.name)
        weak_ids_to_devices[id(device)] = device
    initialise_udc(context, dev_mode)
    devices_after_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )
    for f in fields(devices_after_reset):
        device = getattr(devices_after_reset, f.name)
        weak_ids_to_devices[id(device)] = device
    for f in fields(devices_after_reset):
        device_after_reset = getattr(devices_after_reset, f.name)
        device_before_reset = getattr(devices_before_reset, f.name)
        assert device_before_reset is not device_after_reset, (
            f"{id(device_before_reset)} == {id(device_after_reset)}"
        )
    check_instances_are_garbage_collected(i)
    context.run_engine.loop.call_soon_threadsafe(context.run_engine.loop.stop)


def check_instances_are_garbage_collected(i: int):
    device_counts: dict[str, int] = {}
    for ref in weak_ids_to_devices.valuerefs():
        device = ref()
        if device is not None:
            device_counts[device.name] = device_counts.get(device.name, 0) + 1

    devices_by_count = sorted([(count, name) for name, count in device_counts.items()])
    print(
        f"Dictionary size is {len(weak_ids_to_devices)}, total live references is "
        f"{sum(device_and_count[0] for device_and_count in devices_by_count)}"
    )
    print(
        f"Max count device is {devices_by_count[-1]}, min count device is {devices_by_count[0]}"
    )
    for name, count in device_counts.items():
        max_count = min(MAX_DEVICE_COUNT, i * 2)
        try:
            assert count <= max_count, (
                f"Device count {name} exceeded max expected references {count}"
            )
        except:
            if STOP_ON_LEAK_DETECTION:
                print("assertion failed, Sleeping...")
                sleep(1e6)
            raise
