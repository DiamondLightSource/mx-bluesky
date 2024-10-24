from collections.abc import Callable
from typing import TypeVar

from dodal.common.beamlines.beamline_utils import clear_device
from ophyd_async.core import Device

OADevice = TypeVar("OADevice", bound=Device)


def rebuild_oa_device_as_mocked_if_necessary(factory: Callable[[], OADevice], **kwargs):
    device = factory(**kwargs)
    if not device._previous_connect_was_mock:  # noqa
        clear_device(device.name)
    device = factory(**kwargs)
    return device
