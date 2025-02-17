import dataclasses
from typing import Any, ClassVar, Protocol, TypeVar, get_type_hints

from blueapi.core import BlueskyContext
from blueapi.core.bluesky_types import Device

from mx_bluesky.common.utils.log import LOGGER

T = TypeVar("T", bound=Device)


class _IsDataclass(Protocol):
    """Protocol followed by any dataclass"""

    __dataclass_fields__: ClassVar[dict]


DT = TypeVar("DT", bound=_IsDataclass)


def find_device_in_context(
    context: BlueskyContext,
    name: str,
    # Typing in here is wrong (see https://github.com/microsoft/pyright/issues/7228#issuecomment-1934500232)
    # but this whole thing will go away when we do https://github.com/DiamondLightSource/hyperion/issues/868
    expected_type: type[T] = Device,  # type: ignore
) -> T:
    LOGGER.debug(f"Looking for device {name} of type {expected_type} in context")

    device = context.find_device(name)
    if device is None:
        raise ValueError(
            f"Cannot find device named '{name}' in bluesky context {context.devices}."
        )

    if not isinstance(device, expected_type):
        raise ValueError(
            f"Found device named '{name}' and expected it to be a '{expected_type}' but it was a '{device.__class__.__name__}'"
        )

    LOGGER.debug(f"Found matching device {device}")
    return device


def device_composite_from_context(context: BlueskyContext, dc: type[DT]) -> DT:
    """
    Initializes all of the devices referenced in a given dataclass from a provided
    context, checking that the types of devices returned by the context are compatible
    with the type annotations of the dataclass.

    Note that if the context was not created with `wait_for_connection=True` devices may
    still be unconnected.
    """
    LOGGER.debug(
        f"Attempting to initialize devices referenced in dataclass {dc} from blueapi context"
    )

    devices: dict[str, Any] = {}
    dc_type_hints: dict[str, Any] = get_type_hints(dc)

    for field in dataclasses.fields(dc):
        device = find_device_in_context(
            context, field.name, expected_type=dc_type_hints.get(field.name, Device)
        )

        devices[field.name] = device

    return dc(**devices)
