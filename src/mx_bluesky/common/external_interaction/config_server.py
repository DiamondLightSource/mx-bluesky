from abc import ABC, abstractmethod
from functools import cache

from daq_config_server.client import ConfigServer
from pydantic import BaseModel, Field, model_validator


class FeatureFlags(BaseModel, ABC):
    """Abstract class to use ConfigServer to toggle features for an experiment

    A module wanting to use FeatureFlags should inherit this class, add boolean features
    as attributes, and implement a get_config_server method, which returns a cached creation of
    ConfigServer. See HyperionFeatureFlags for an example

    Values supplied upon class instantiation will always take priority over the config server. If connection to the server cannot
    be made AND values were not supplied, attributes will use their default values
    """

    # Feature values supplied at construction will override values from the config server
    overriden_features: dict = Field(default_factory=dict, exclude=True)

    @staticmethod
    @cache
    @abstractmethod
    def get_config_server() -> ConfigServer: ...

    @model_validator(mode="before")
    @classmethod
    def mark_overridden_features(cls, values):
        assert isinstance(values, dict)
        values["overriden_features"] = values.copy()
        cls._validate_overridden_features(values)
        return values

    @classmethod
    def _validate_overridden_features(cls, values: dict):
        """Validates overridden features to ensure they are defined in the model fields."""
        defined_fields = cls.model_fields.keys()
        invalid_features = [key for key in values.keys() if key not in defined_fields]

        if invalid_features:
            message = f"Invalid feature toggle(s) supplied: {invalid_features}. "
            raise ValueError(message)

    def _get_flags(self):
        flags = type(self).get_config_server().best_effort_get_all_feature_flags()
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
