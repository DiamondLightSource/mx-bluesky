from blueapi.core import BlueskyContext
from dodal.common.beamlines.beamline_utils import clear_devices
from dodal.utils import collect_factories, get_beamline_based_on_environment_variable


def setup_context(dev_mode: bool = False) -> BlueskyContext:
    context = BlueskyContext()
    setup_devices(context, dev_mode)
    return context


def clear_all_device_caches(context: BlueskyContext):
    context.unregister_all_devices()
    clear_devices()

    for f in collect_factories(get_beamline_based_on_environment_variable()).values():
        if hasattr(f, "cache_clear"):
            f.cache_clear()  # type: ignore


def setup_devices(context: BlueskyContext, dev_mode: bool):
    _, exceptions = context.with_device_manager(
        get_beamline_based_on_environment_variable().devices,
        mock=dev_mode,
    )
    if exceptions:
        raise ExceptionGroup(
            f"Unable to connect to beamline devices {list(exceptions.keys())}",
            list(exceptions.values()),
        )
