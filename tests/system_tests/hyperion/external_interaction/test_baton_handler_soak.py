import gc
import os
from dataclasses import fields
from unittest.mock import patch
from weakref import WeakValueDictionary

import pytest
from blueapi.core import BlueskyContext
from bluesky import RunEngine
from ophyd_async.core import Device
from ophyd_async.plan_stubs import ensure_connected

from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.hyperion.baton_handler import _initialise_udc
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.utils.context import setup_context

weak_ids_to_devices = WeakValueDictionary()


MAX_DEVICE_COUNT = 4


@pytest.fixture
def patch_setup_devices(request):
    dev_mode = request.param
    from mx_bluesky.hyperion.utils.context import setup_devices

    def patched_setup_devices(context: BlueskyContext, _: bool):
        setup_devices(context, dev_mode)

    with patch(
        "mx_bluesky.hyperion.baton_handler.setup_devices",
        side_effect=patched_setup_devices,
    ) as patched_func:
        yield patched_func


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


@pytest.mark.parametrize(
    "i, patch_setup_devices",
    [[i, True] for i in range(1, 101)],
    indirect=["patch_setup_devices"],
)
@pytest.mark.system_test
@patch.dict(os.environ, {"BEAMLINE": "i03"})
def test_udc_reloads_all_devices_soak_test_dev_mode(
    RE: RunEngine, i: int, patch_setup_devices
):
    reinitialise_beamline(True, i)


@pytest.mark.parametrize(
    "i, patch_setup_devices",
    [[i, False] for i in range(1, 101)],
    indirect=["patch_setup_devices"],
)
@patch.dict(os.environ, {"BEAMLINE": "i03"})
@patch("ophyd_async.plan_stubs._ensure_connected.DEFAULT_TIMEOUT", 1)
@pytest.mark.timeout(10)
def test_udc_reloads_all_devices_soak_test_real(
    RE: RunEngine, i: int, patch_setup_devices, patch_ensure_connected
):
    """
    Deliberately not part of main system tests because this is SLOW and requires
    a beamline to connect to.
    """
    reinitialise_beamline(False, i)


def reinitialise_beamline(dev_mode: bool, i: int):
    """Reinitialise the beamline, which should cause all beamline devices
    to be reinstantiated, and then check for memory leaks (potentially caused
    if something holds a reference to the device).
    Since GC is in general implementation dependent and non-deterministic,
    it is not guaranteed that devices will be collected after only one iteration.
    Therefore this test is run a number of times in a loop and we check that the
    outstanding instances do not exceed some threshold value."""

    context = setup_context(dev_mode)
    devices_before_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )
    for f in fields(devices_before_reset):
        device = getattr(devices_before_reset, f.name)
        weak_ids_to_devices[id(device)] = device
    _initialise_udc(context, dev_mode)
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
    gc.collect()
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
        assert count <= max_count, (
            f"Device count {name} exceeded max expected references {count}"
        )
