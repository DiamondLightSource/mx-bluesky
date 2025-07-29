import json
from dataclasses import fields
from enum import Enum
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

FEATURE_FLAG_CACHE_LENGTH_S = 60 * 5

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
        self._time_of_last_feature_get: float = 0
        self._verify_feature_parameters()
        super().__init__(url)

    def _verify_feature_parameters(self):
        sources_keys = {feature.name for feature in self.feature_sources}
        feature_dc_keys = {key.name for key in fields(self.feature_dc)}
        assert sources_keys == feature_dc_keys, (
            f"MXConfig server feature_sources names do not match feature_dc keys: {sources_keys} != {feature_dc_keys}"
        )

    def _get_oav_config(self, reset_cached_result=False) -> dict[str, Any]:
        """
        Args:
        reset_cached_result (bool): Force refresh the cache for this request
        """
        if reset_cached_result:
            self._cached_oav_config = None
        if not self._cached_oav_config:
            config_path = OavConstants.OAV_CONFIG_JSON
            try:
                self._cached_oav_config = TypeAdapter(dict[str, Any]).validate_python(
                    self.get_file_contents(
                        config_path, dict, reset_cached_result=reset_cached_result
                    )
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

    def get_oav_config(self) -> dict[str, Any]:
        """Get the OAV config in the form of a python dictionary. Store results in a cache
        which should be updated at the start of a plan using self.refresh_cache()
        """
        return self._get_oav_config()

    def _check_missing_fields(self, expected: set, actual: set):
        missing = expected - actual
        if missing:
            LOGGER.warning(
                f"Missing features from domain.properties: {missing}.\n Using defaults for missing features"
            )

    def _get_feature_flags(self, reset_cached_result=False) -> T:
        """
        Args:
        reset_cached_result (bool): Force refresh the cache for this request
        """

        try:
            if reset_cached_result:
                self._cached_features = None
            if not self._cached_features:
                self._cached_features = None
                # Construct self.feature_dc by reading the domain.properties file
                all_features = list(self.feature_sources)
                feature_dict = {}
                domain_properties = self.get_file_contents(
                    GDA_DOMAIN_PROPERTIES_PATH, reset_cached_result=reset_cached_result
                ).splitlines()
                for line in domain_properties:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    line = line.split("#", 1)[0].strip()  # Remove inline comments
                    if "=" in line:
                        key, value = map(str.strip, line.split("=", 1))
                        for feature in all_features:
                            assert isinstance(feature, Enum)
                            if key == feature.value:
                                feature_dict[feature.name] = value
                self._check_missing_fields(
                    {f.name for f in fields(self.feature_dc)}, set(feature_dict.keys())
                )
                self._cached_features = self.feature_dc(**feature_dict)
            return self._cached_features
        except Exception as e:
            LOGGER.warning(
                f"Failed to get feature flags from config server: {e} \nUsing defaults..."
            )
            return self.feature_dc()

    def get_feature_flags(self) -> T:
        """Get feature flags by making a request to the config server. If the request fails, use the hardcoded defaults. Store results in a cache
        which should be updated at the start of a plan using self.refresh_cache()
        """
        return self._get_feature_flags()

    def refresh_cache(self):
        """Refresh the client's cache. Use at the beginning of a plan"""
        self._get_feature_flags(reset_cached_result=True)
        self._get_oav_config(reset_cached_result=True)
