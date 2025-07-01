from functools import cache

from daq_config_server.client import ConfigServer

from mx_bluesky.common.external_interaction.config_server import FeatureFlags
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


class HyperionFeatureFlags(FeatureFlags):
    """
    Feature flags specific to Hyperion.

    Attributes:
        use_panda_for_gridscan:         If True then the PandA is used for gridscans, otherwise the zebra is used
        use_gpu_results:                If True then GPU result processing is enabled
            and the GPU result is taken.
        set_stub_offsets:               If True then set the stub offsets after moving to the crystal (ignored for
            multi-centre)
        omega_flip:                     If True then invert the smargon omega motor rotation commands with respect to
         the hyperion request. See "Hyperion Coordinate Systems" in the documentation.
        alert_manager_url:              Base URL for alertmanager, if using for alerting.
        alternate_rotation_direction:   If True then the for multi-sample pins the rotation direction of
         successive rotation scans is alternated between positive and negative.
    """

    @staticmethod
    @cache
    def get_config_server() -> ConfigServer:
        return ConfigServer(CONST.CONFIG_SERVER_URL, LOGGER)

    use_panda_for_gridscan: bool = CONST.I03.USE_PANDA_FOR_GRIDSCAN
    use_gpu_results: bool = CONST.I03.USE_GPU_RESULTS
    set_stub_offsets: bool = CONST.I03.SET_STUB_OFFSETS
    omega_flip: bool = CONST.I03.OMEGA_FLIP
    alert_manager_url: str = CONST.I03.ALERT_MANAGER_URL
    alternate_rotation_direction: bool = CONST.I03.ALTERNATE_ROTATION_DIRECTION
