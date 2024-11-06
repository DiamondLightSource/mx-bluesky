from abc import ABC, abstractmethod

from daq_config_server.client import ConfigServer
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeatureFlags(BaseModel, ABC):
    """Common interface to use ConfigServer to toggle features for an experiment. To use, inherit this class and add desired features as attributes along with
    the actual config server"""

    # The default value will be used as the fallback when doing a best-effort fetch
    # from the service

    # Feature values supplied at construction will override values from the config server
    overriden_features: dict = Field(default_factory=dict, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @abstractmethod
    def get_config_server(self) -> ConfigServer: ...

    @model_validator(mode="before")
    @classmethod
    def mark_overridden_features(cls, values):
        assert isinstance(values, dict)
        values["overriden_features"] = values.copy()
        return values

    def _get_flags(self):
        flags = self.get_config_server().best_effort_get_all_feature_flags()
        return {f: flags[f] for f in flags if f in self.model_fields.keys()}

    def update_self_from_server(self):
        """Used to update the feature flags from the server during a plan. Where there are flags which were explicitly set from externally supplied parameters, these values will be used instead."""
        for flag, value in self._get_flags().items():
            updated_value = (
                value
                if flag not in self.overriden_features.keys()
                else self.overriden_features[flag]
            )
            setattr(self, flag, updated_value)
