from logging import Logger
from time import time
from typing import Any, Generic, TypeVar

from daq_config_server.client import ConfigServer
from pydantic import TypeAdapter

from mx_bluesky.common.parameters.constants import (
    GDA_DOMAIN_PROPERTIES_PATH,
    FeatureFlags,
    FeatureFlagSources,
    OavConstants,
)

FEATURE_FLAG_CACHE_LENGTH = 60 * 5


"""Make methods to get the specific bits we need in nicely formatted ways. Wrap around a try so we try to read from /dls_sw if the config server fails"""

T = TypeVar("T", bound=FeatureFlags)


class MXConfigServer(ConfigServer, Generic[T]):
    def __init__(
        self,
        url: str,
        feature_sources: type[FeatureFlagSources],
        feature_dc: type[T],
        log: Logger | None = None,
    ):
        self.feature_sources = feature_sources
        self.feature_dc: type[T] = feature_dc
        self._cached_features: T | None = None
        self._time_since_feature_get: float = 0
        super().__init__(url, log)

    # todo put in a try block?
    def get_oav_config(self) -> dict[str, Any]:
        config_path = OavConstants.OAV_CONFIG_JSON
        return TypeAdapter(dict[str, Any]).validate_python(
            self.get_file_contents(config_path, dict)
        )

    def get_feature_flags(self, refresh=False) -> T:
        if (
            refresh
            or not self._cached_features
            or time() - self._time_since_feature_get > FEATURE_FLAG_CACHE_LENGTH
        ):
            feature_dict = {}
            domain_properties = self.get_file_contents(
                GDA_DOMAIN_PROPERTIES_PATH
            ).splitlines()
            for line in domain_properties:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                line = line.split("#", 1)[0].strip()  # Remove inline comments
                if "=" in line:
                    key, value = map(str.strip, line.split("=", 1))
                    # Can just use "in" as of python 3.12
                    if key in self.feature_sources._value2member_map_:
                        feature_dict[key] = value
            # TODO put all this in try
            self._time_since_feature_get = time()
            self._cached_features = self.feature_dc(**feature_dict)
        return self._cached_features


# my_server = MXConfigServer("https://daq-config.diamond.ac.uk")
# data = my_server.get_file_contents(
#     "/dls_sw/i03/software/daq_configuration/json/OAVCentring_hyperion.json",
#     desired_return_type=str,
#     reset_cached_result=False,
# )
# print(data)


# class FeatureFlags(BaseModel, ABC):
#     """Abstract class to use ConfigServer to toggle features for an experiment

#     A module wanting to use FeatureFlags should inherit this class, add boolean features
#     as attributes, and implement a get_config_server method, which returns a cached creation of
#     ConfigServer. See HyperionFeatureFlags for an example

#     Values supplied upon class instantiation will always take priority over the config server. If connection to the server cannot
#     be made AND values were not supplied, attributes will use their default values
#     """

#     # Feature values supplied at construction will override values from the config server
#     overriden_features: dict = Field(default_factory=dict, exclude=True)

#     @staticmethod
#     @cache
#     @abstractmethod
#     def get_config_server() -> ConfigServer: ...

#     @model_validator(mode="before")
#     @classmethod
#     def mark_overridden_features(cls, values):
#         assert isinstance(values, dict)
#         values["overriden_features"] = values.copy()
#         cls._validate_overridden_features(values)
#         return values

#     @classmethod
#     def _validate_overridden_features(cls, values: dict):
#         """Validates overridden features to ensure they are defined in the model fields."""
#         defined_fields = cls.model_fields.keys()
#         invalid_features = [key for key in values.keys() if key not in defined_fields]

#         if invalid_features:
#             message = f"Invalid feature toggle(s) supplied: {invalid_features}. "
#             raise ValueError(message)

#     def _get_flags(self):
#         flags = type(self).get_config_server().best_effort_get_all_feature_flags()
#         return {f: flags[f] for f in flags if f in self.model_fields.keys()}

#     def update_self_from_server(self):
#         """Used to update the feature flags from the server during a plan. Where there are flags which were explicitly set from externally supplied parameters, these values will be used instead."""
#         for flag, value in self._get_flags().items():
#             updated_value = (
#                 value
#                 if flag not in self.overriden_features.keys()
#                 else self.overriden_features[flag]
#             )
#             setattr(self, flag, updated_value)
