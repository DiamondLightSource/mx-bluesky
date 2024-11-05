from collections.abc import Callable
from typing import TypeVar

from dodal.common.beamlines.beamline_utils import clear_device
from ophyd_async.core import Device

OADevice = TypeVar("OADevice", bound=Device)


def rebuild_oa_device_as_mocked_if_necessary(factory: Callable[[], OADevice], **kwargs):
    """Rebuild the device if it was previously connected as real not fake - this
    is usually due to being instantiated as a default parameter value to a bluesky plan
    on module load"""
    device = factory(**kwargs)
    if not device._connect_mock_arg:  # noqa
        clear_device(device.name)
    device = factory(**kwargs)
    return device
