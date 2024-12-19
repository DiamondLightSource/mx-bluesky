"""
TODO:
- Get good way to setup logging on plan startup


This overall plan should:
- Setup graylog (for now), and link to https://github.com/DiamondLightSource/blueapi/issues/583
- Do snapshots (maybe in different ticket)
- Accept grid scan params from GDA
- Do FGS and trigger zocalo but don't wait on zocalo
- Push results to ispyb

- see https://github.com/DiamondLightSource/hyperion/pull/942/files to see what old plan was doing
- see https://github.com/DiamondLightSource/dodal/pull/211 for the old dodal change
"""


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite:
    """All devices which are directly or indirectly required by this plan"""

    attenuator: Attenuator
    backlight: Backlight
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    synchrotron: Synchrotron
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    # sample_shutter: ZebraShutter

    @property
    def sample_motors(self) -> Smargon:
        """Convenience alias with a more user-friendly name"""
        return self.smargon
