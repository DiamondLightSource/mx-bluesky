from functools import cache

from daq_config_server.client import ConfigServer

from mx_bluesky.common.external_interaction.config_server import FeatureFlags
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


# Strange-looking: see https://docs.astral.sh/ruff/rules/cached-instance-method/
@cache
def config_server() -> ConfigServer:
    return ConfigServer(CONST.CONFIG_SERVER_URL, LOGGER)


class HyperionFeatureFlags(FeatureFlags):
    def get_config_server(self) -> ConfigServer:
        return config_server()

    use_panda_for_gridscan: bool = CONST.I03.USE_PANDA_FOR_GRIDSCAN
    compare_cpu_and_gpu_zocalo: bool = CONST.I03.COMPARE_CPU_AND_GPU_ZOCALO
    set_stub_offsets: bool = CONST.I03.SET_STUB_OFFSETS
