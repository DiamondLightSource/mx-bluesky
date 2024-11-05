from mx_bluesky.common.external_interaction.config_server import FeatureFlags
from mx_bluesky.hyperion.parameters.constants import CONST


class HyperionFeatureFlags(FeatureFlags):
    config_server_url: str = CONST.CONFIG_SERVER_URL
    use_panda_for_gridscan: bool = CONST.I03.USE_PANDA_FOR_GRIDSCAN
    compare_cpu_and_gpu_zocalo: bool = CONST.I03.COMPARE_CPU_AND_GPU_ZOCALO
    set_stub_offsets: bool = CONST.I03.SET_STUB_OFFSETS
