from blueapi.core import BlueskyContext
from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.utils import get_beamline_based_on_environment_variable


def setup_context(dev_mode: bool = False) -> BlueskyContext:
    context = BlueskyContext()
    setup_devices(context, dev_mode)
    return context


def clear_all_device_caches(context: BlueskyContext):
    context.unregister_all_devices()
    get_config_client().reset_cache()


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
