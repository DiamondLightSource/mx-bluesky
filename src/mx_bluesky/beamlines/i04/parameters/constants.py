from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    FeatureSettings,
    FeatureSettingSources,
)


# These currently exist in GDA domain.properties
class I04FeatureSettingsSources(FeatureSettingSources):
    ASSUMED_WAVELENGTH_IN_A = "gda.px.expttable.default.wavelength"


# Use these defaults if we can't read from the config server
@dataclass
class I04FeatureSettings(FeatureSettings):
    ASSUMED_WAVELENGTH_IN_A: float = 0.95373
