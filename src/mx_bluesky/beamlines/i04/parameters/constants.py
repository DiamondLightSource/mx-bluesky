from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    FeatureSettings,
    FeatureSettingSources,
)


# These currently exist in GDA domain.properties
class I04FeatureSettingsSources(FeatureSettingSources):
    ASSUMED_WAVELENGTH_IN_A = "gda.px.expttable.default.wavelength"
    XRC_UNSCALED_TRANSMISSION_FRAC = "gda.mx.bluesky.i04.xrc.unscaled_transmission_frac"
    XRC_UNSCALED_EXPOSURE_TIME_S = "gda.mx.bluesky.i04.xrc.unscaled_exposure_time_s"


# Use these defaults if we can't read from the config server
@dataclass
class I04FeatureSettings(FeatureSettings):
    ASSUMED_WAVELENGTH_IN_A: float = 0.95373
    XRC_UNSCALED_TRANSMISSION_FRAC: int = 1
    XRC_UNSCALED_EXPOSURE_TIME_S: float = 0.007
