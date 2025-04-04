from functools import cache

from daq_config_server.client import ConfigServer
from pydantic import model_validator

from mx_bluesky.common.external_interaction.config_server import FeatureFlags
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


class HyperionFeatureFlags(FeatureFlags):
    """
    Feature flags specific to Hyperion.

    Attributes:
        use_panda_for_gridscan:         If True then the PandA is used for gridscans, otherwise the zebra is used
        compare_cpu_and_gpu_zocalo:     If True then GPU result processing is enabled
            alongside CPU and the results are compared. The CPU result is still take.n
        use_gpu_results:                If True then GPU result processing is enabled
            and the GPU result is taken.
        set_stub_offsets:               If True then set the stub offsets after moving to the crystal (ignored for
            multi-centre)
        omega_flip:                     If True then invert the smargon omega motor rotation commands with respect to
         the hyperion request.
    """

    @staticmethod
    @cache
    def get_config_server() -> ConfigServer:
        return ConfigServer(CONST.CONFIG_SERVER_URL, LOGGER)

    @model_validator(mode="after")
    def use_gpu_and_compare_cannot_both_be_true(self):
        assert not (self.use_gpu_results and self.compare_cpu_and_gpu_zocalo), (
            "Cannot both use GPU results and compare them to CPU"
        )
        return self

    use_panda_for_gridscan: bool = CONST.I03.USE_PANDA_FOR_GRIDSCAN
    compare_cpu_and_gpu_zocalo: bool = CONST.I03.COMPARE_CPU_AND_GPU_ZOCALO
    use_gpu_results: bool = CONST.I03.USE_GPU_RESULTS
    set_stub_offsets: bool = CONST.I03.SET_STUB_OFFSETS
    omega_flip: bool = CONST.I03.OMEGA_FLIP
