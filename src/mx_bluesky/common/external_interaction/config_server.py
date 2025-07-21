import json
from dataclasses import fields
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
from mx_bluesky.common.utils.log import LOGGER

FEATURE_FLAG_CACHE_LENGTH = 60 * 5


"""Make methods to get the specific bits we need in nicely formatted ways. Wrap around a try so we try to read from /dls_sw if the config server fails"""

T = TypeVar("T", bound=FeatureFlags)


class MXConfigServer(ConfigServer, Generic[T]):
    def __init__(
        self,
        feature_sources: type[FeatureFlagSources],
        feature_dc: type[T],
        url: str = "https://daq-config.diamond.ac.uk",
    ):
        """MX implementation of the config server client. Makes requests to the config server to retrieve config while falling back to
        the filesystem in the case that the request failed.

        See mx_bluesky/hyperion/external_interaction/config_server.py for example implementation.

        Args:
        feature_sources: A StrEnum containing available features, where the string is the name of that feature toggle in a beamline's GDA
        domain.properties.

        feature_dc: A dataclass containing available features along with their default flags. This dataclass must contain the same keys
        as the feature_sources parameter. These defaults are used when a server request fails.
        """

        self.feature_sources = feature_sources
        self.feature_dc: type[T] = feature_dc
        self._cached_features: T | None = None
        self._cached_oav_config: dict[str, Any] | None = None
        self._time_since_feature_get: float = 0
        self._verify_feature_parameters()
        super().__init__(url)

    def _verify_feature_parameters(self):
        sources_keys = [feature.name for feature in self.feature_sources]
        feature_dc_keys = [key.name for key in fields(self.feature_dc)]
        assert sources_keys == feature_dc_keys, (
            f"MXConfig server feature_sources names do not match feature_dc keys: {sources_keys} != {feature_dc_keys}"
        )

    def get_oav_config(self) -> dict[str, Any]:
        if not self._cached_oav_config:
            config_path = OavConstants.OAV_CONFIG_JSON
            try:
                self._cached_oav_config = TypeAdapter(dict[str, Any]).validate_python(
                    self.get_file_contents(config_path, dict)
                )
            except Exception as e:
                LOGGER.warning(
                    f"Failed to get oav config from config server: {e} \nReading the file directory..."
                )
                with open(config_path) as f:
                    self._cached_oav_config = TypeAdapter(
                        dict[str, Any]
                    ).validate_python(json.loads(f.read()))
        return self._cached_oav_config

    def get_feature_flags(self) -> T:
        """Get feature flags by making a request to the config server. If the request fails, use the hardcoded defaults"""

        try:
            if (
                not self._cached_features
                or time() - self._time_since_feature_get > FEATURE_FLAG_CACHE_LENGTH
            ):
                # Return self.feature_dc based off the settings defined in the domain.properties file
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
                self._time_since_feature_get = time()
                self._cached_features = self.feature_dc(**feature_dict)
            return self._cached_features
        except Exception as e:
            LOGGER.warning(
                f"Failed to get feature flags from config server: {e} \nUsing defaults..."
            )
            return self.feature_dc()

    def clear_cache(self):
        "Clear the client's cache. Use when filesystem config may have changed"
        self._cached_features = None
        self._cached_oav_config = None
