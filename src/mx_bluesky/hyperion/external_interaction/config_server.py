from daq_config_server.client import ConfigServer
from pydantic import BaseModel, Field, model_validator

from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST

_CONFIG_SERVER: ConfigServer | None = None


def config_server() -> ConfigServer:
    global _CONFIG_SERVER
    if _CONFIG_SERVER is None:
        _CONFIG_SERVER = ConfigServer(CONST.CONFIG_SERVER_URL, LOGGER)
    return _CONFIG_SERVER


class FeatureFlags(BaseModel):
    # The default value will be used as the fallback when doing a best-effort fetch
    # from the service
    use_panda_for_gridscan: bool = CONST.I03.USE_PANDA_FOR_GRIDSCAN
    compare_cpu_and_gpu_zocalo: bool = CONST.I03.COMPARE_CPU_AND_GPU_ZOCALO
    set_stub_offsets: bool = CONST.I03.SET_STUB_OFFSETS

    # Feature values supplied at construction will override values from the config server
    overriden_features: dict = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def mark_overridden_features(cls, values):
        assert isinstance(values, dict)
        values["overriden_features"] = values.copy()
        return values

    @classmethod
    def _get_flags(cls):
        flags = config_server().best_effort_get_all_feature_flags()
        return {f: flags[f] for f in flags if f in cls.model_fields.keys()}

    def update_self_from_server(self):
        """Used to update the feature flags from the server during a plan. Where there are flags which were explicitly set from externally supplied parameters, these values will be used instead."""
        for flag, value in self._get_flags().items():
            updated_value = (
                value
                if flag not in self.overriden_features.keys()
                else self.overriden_features[flag]
            )
            setattr(self, flag, updated_value)
