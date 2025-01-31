# """
# TODO:
# - Get good way to setup logging on plan startup


# This overall plan should:
# - Setup graylog (for now), and link to https://github.com/DiamondLightSource/blueapi/issues/583
# - Do snapshots (maybe in different ticket)
# - Accept grid scan params from GDA
# - Do FGS and trigger zocalo but don't wait on zocalo
# - Push results to ispyb

# -Should we also automatically move to the centre of the crystal? Probably not as vmxm mainly use FGS just to check if crystal diffracts. (ask though)

# - see https://github.com/DiamondLightSource/hyperion/pull/942/files to see what old plan was doing
# - see https://github.com/DiamondLightSource/dodal/pull/211 for the old dodal change


# Create common interface for all this stuff so that all this shared logic between hyperion isn't duplicated
# """

# from functools import partial

# import bluesky.plan_stubs as bps
# import bluesky.preprocessors as bpp
# import numpy as np
# import pydantic
# from bluesky.utils import MsgGenerator
# from dodal.common import inject
# from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
# from dodal.devices.backlight import Backlight
# from dodal.devices.eiger import EigerDetector
# from dodal.devices.fast_grid_scan import FastGridScanCommon, ZebraFastGridScan
# from dodal.devices.fast_grid_scan import (
#     set_fast_grid_scan_params as set_flyscan_params_plan,
# )
# from dodal.devices.smargon import Smargon
# from dodal.devices.synchrotron import Synchrotron
# from dodal.devices.xbpm_feedback import XBPMFeedback
# from dodal.devices.zebra.zebra import Zebra
# from dodal.devices.zocalo.zocalo_results import (
#     ZOCALO_READING_PLAN_NAME,
#     ZOCALO_STAGE_GROUP,
#     XrcResult,
#     ZocaloResults,
#     get_full_processing_results,
# )

# from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
#     setup_zebra_for_xrc_flyscan,
#     tidy_up_zebra_after_gridscan,
# )
# from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
#     transmission_and_xbpm_feedback_for_collection_decorator,
# )
# from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
#     ispyb_activation_wrapper,
# )
# from mx_bluesky.common.parameters.constants import (
#     EnvironmentConstants,
#     GridscanParamConstants,
#     PlanGroupCheckpointConstants,
#     PlanNameConstants,
# )
# from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
# from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
#     BeamlineSpecificFGSFeatures,
#     FlyScanEssentialDevices,
#     ReadHardwareTime,
#     read_hardware,
# )
# from mx_bluesky.common.plans.do_fgs import kickoff_and_complete_gridscan
# from mx_bluesky.common.utils.exceptions import CrystalNotFoundException, SampleException
# from mx_bluesky.common.utils.log import LOGGER
# from mx_bluesky.common.utils.tracing import TRACER
# from mx_bluesky.common.xrc_result import XRayCentreEventHandler, XRayCentreResult
# from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
#     _fire_xray_centre_result_event,
# )

# # TODO: identify the differences:
# """
# in VMXM: We don't need the aperture scatterguard - don't move aperture
# Slit gaps and dcm and undulator may not be needed to be read, so different read hardware plan
# Don't use panda - different setup and tidy
# Sample shutter - unclear how this works for vmxm
# """


# @pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
# class FlyScanXRayCentreComposite(FlyScanEssentialDevices):
#     """All devices which are directly or indirectly required by this plan"""

#     attenuator: EnumFilterAttenuator

#     @property
#     def sample_motors(self) -> Smargon:
#         """Convenience alias with a more user-friendly name"""
#         return self.smargon


# def _get_feature_controlled(
#     fgs_composite: FlyScanXRayCentreComposite,
#     parameters: SpecifiedThreeDGridScan,
# ):
#     return BeamlineSpecificFGSFeatures(
#         setup_trigger_plan=_zebra_triggering_setup,
#         tidy_plan=partial(_tidy_plan, group="flyscan_zebra_tidy", wait=True),
#         set_flyscan_params_plan=partial(
#             set_flyscan_params_plan,
#             fgs_composite.zebra_fast_grid_scan,
#             parameters.FGS_params,
#         ),
#         fgs_motors=fgs_composite.zebra_fast_grid_scan,
#     )


# # For now, VMXM Zebra settings are never changed in Bluesky plans.
# # Let GDA and motion programs handle zebra/fast shutter
# def _zebra_triggering_setup(
#     fgs_composite: FlyScanXRayCentreComposite,
#     parameters: SpecifiedThreeDGridScan,
# ):
#     yield from setup_zebra_for_xrc_flyscan(fgs_composite.zebra)


# def _tidy_plan(
#     fgs_composite: FlyScanXRayCentreComposite, group, wait=True
# ) -> MsgGenerator:
#     LOGGER.info("Tidying up Zebra")
#     yield from tidy_up_zebra_after_gridscan(fgs_composite.zebra)
#     LOGGER.info("Tidying up Zocalo")
#     # make sure we don't consume any other results
#     yield from bps.unstage(fgs_composite.zocalo, group=group, wait=wait)


# def flyscan_xray_centre(
#     parameters: SpecifiedThreeDGridScan,
#     attenuator: EnumFilterAttenuator = inject("attenuator"),
#     backlight: Backlight = inject("backlight"),
#     eiger: EigerDetector = inject("eiger"),
#     zebra_fast_grid_scan: ZebraFastGridScan = inject("zebra_fast_grid_scan"),
#     synchrotron: Synchrotron = inject("synchrotron"),
#     xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
#     zebra: Zebra = inject("zebra"),
#     zocalo: ZocaloResults = inject("zocalo"),
#     smargon: Smargon = inject("smargon"),
# ):
#     """Add a docstring"""
#     # Composites have to be made this way until https://github.com/DiamondLightSource/dodal/issues/874
#     # is done and we can properly use composite devices in BlueAPI
#     composite = FlyScanXRayCentreComposite(
#         attenuator,
#         backlight,
#         eiger,
#         zebra_fast_grid_scan,
#         synchrotron,
#         xbpm_feedback,
#         zebra,
#         zocalo,
#         smargon,
#     )
#     xrc_event_handler = XRayCentreEventHandler()

#     feature_controlled = _get_feature_controlled(composite, parameters)

#     @bpp.subs_decorator(xrc_event_handler)
#     def flyscan_and_fetch_results() -> MsgGenerator:
#         yield from ispyb_activation_wrapper(
#             flyscan_xray_centre_no_move(composite, parameters, feature_controlled),
#             parameters,
#         )

#     yield from flyscan_and_fetch_results()

#     xray_centre_results = xrc_event_handler.xray_centre_results
#     assert xray_centre_results, (
#         "Flyscan result event not received or no crystal found and exception not raised"
#     )

#     # Typing complains if you don't put parameters here
#     yield from feature_controlled.plan_using_xrc_results(
#         composite, parameters, xray_centre_results[0]
#     )


# def flyscan_xray_centre_no_move(
#     composite: FlyScanXRayCentreComposite,
#     parameters: SpecifiedThreeDGridScan,
#     feature_controlled: BeamlineSpecificFGSFeatures,
# ):
#     composite.eiger.set_detector_parameters(parameters.detector_params)
#     composite.zocalo.zocalo_environment = EnvironmentConstants.ZOCALO_ENV

#     @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
#     @bpp.run_decorator(  # attach experiment metadata to the start document
#         md={
#             "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
#             "mx_bluesky_parameters": parameters.model_dump_json(),
#             "activate_callbacks": [
#                 "GridscanNexusFileCallback",
#             ],
#         }
#     )
#     @bpp.finalize_decorator(lambda: feature_controlled.tidy_plan)
#     @transmission_and_xbpm_feedback_for_collection_decorator(
#         composite.xbpm_feedback,
#         composite.attenuator,
#         parameters.transmission_frac,
#     )
#     def run_gridscan_and_fetch_results_and_tidy(
#         fgs_composite: FlyScanXRayCentreComposite,
#         params: SpecifiedThreeDGridScan,
#         feature_controlled: BeamlineSpecificFGSFeatures,
#     ) -> MsgGenerator:
#         yield from run_gridscan_and_fetch_results(
#             fgs_composite, params, feature_controlled
#         )

#     yield from run_gridscan_and_fetch_results_and_tidy(
#         composite, parameters, feature_controlled
#     )


# @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_AND_MOVE)
# @bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_AND_MOVE})
# def run_gridscan_and_fetch_results(
#     fgs_composite: FlyScanXRayCentreComposite,
#     parameters: SpecifiedThreeDGridScan,
#     feature_controlled: BeamlineSpecificFGSFeatures,
# ) -> MsgGenerator:
#     """A multi-run plan which runs a gridscan, gets the results from zocalo
#     and fires an event with the centres of mass determined by zocalo"""

#     yield from feature_controlled.setup_trigger_plan(fgs_composite, parameters)

#     LOGGER.info("Starting grid scan")
#     yield from bps.stage(
#         fgs_composite.zocalo, group=ZOCALO_STAGE_GROUP
#     )  # connect to zocalo and make sure the queue is clear
#     yield from run_gridscan(fgs_composite, parameters, feature_controlled)

#     LOGGER.info("Grid scan finished, getting results.")

#     try:
#         with TRACER.start_span("wait_for_zocalo"):
#             yield from bps.trigger_and_read(
#                 [fgs_composite.zocalo], name=ZOCALO_READING_PLAN_NAME
#             )
#             LOGGER.info("Zocalo triggered and read, interpreting results.")
#             xrc_results = yield from get_full_processing_results(fgs_composite.zocalo)
#             LOGGER.info(f"Got xray centres, top 5: {xrc_results[:5]}")
#             filtered_results = [
#                 result
#                 for result in xrc_results
#                 if result["total_count"]
#                 >= GridscanParamConstants.ZOCALO_MIN_TOTAL_COUNT_THRESHOLD
#             ]
#             discarded_count = len(xrc_results) - len(filtered_results)
#             if discarded_count > 0:
#                 LOGGER.info(
#                     f"Removed {discarded_count} results because below threshold"
#                 )
#             if filtered_results:
#                 flyscan_results = [
#                     _xrc_result_in_boxes_to_result_in_mm(xr, parameters)
#                     for xr in filtered_results
#                 ]
#             else:
#                 LOGGER.warning("No X-ray centre received")
#                 raise CrystalNotFoundException()
#             yield from _fire_xray_centre_result_event(flyscan_results)

#     finally:
#         # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
#         LOGGER.info("Turning off Eiger dev/shm streaming")
#         yield from bps.abs_set(fgs_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

#         # Wait on everything before returning to GDA (particularly apertures), can be removed
#         # when we do not return to GDA here
#         yield from bps.wait()


# @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_MAIN)
# @bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_MAIN})
# def run_gridscan(
#     fgs_composite: FlyScanXRayCentreComposite,
#     parameters: SpecifiedThreeDGridScan,
#     feature_controlled: BeamlineSpecificFGSFeatures,
#     md={  # noqa
#         "plan_name": PlanNameConstants.GRIDSCAN_MAIN,
#     },
# ):
#     # Currently gridscan only works for omega 0, see #
#     with TRACER.start_span("moving_omega_to_0"):
#         yield from bps.abs_set(fgs_composite.smargon.omega, 0)

#     # We only subscribe to the communicator callback for run_gridscan, so this is where
#     # we should generate an event reading the values which need to be included in the
#     # ispyb deposition
#     with TRACER.start_span("ispyb_hardware_readings"):
#         # TODO: This part will need to be a part of feature control (eg devices that want reading)
#         yield from read_hardware(
#             [
#                 fgs_composite.synchrotron.synchrotron_mode,
#                 fgs_composite.smargon.x,
#                 fgs_composite.smargon.y,
#                 fgs_composite.smargon.z,
#             ],
#             ReadHardwareTime.PRE_COLLECTION,
#         )

#     read_during_collection = partial(
#         read_hardware,
#         [
#             fgs_composite.attenuator.actual_transmission,
#             fgs_composite.eiger.bit_depth,  # type: ignore # Typing doesn't think old ophyd signals are readable
#         ],
#         ReadHardwareTime.DURING_COLLECTION,
#     )

#     LOGGER.info("Setting fgs params")
#     yield from feature_controlled.set_flyscan_params_plan()

#     LOGGER.info("Waiting for gridscan validity check")
#     yield from wait_for_gridscan_valid(feature_controlled.fgs_motors)

#     LOGGER.info("Waiting for arming to finish")
#     yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)
#     yield from bps.stage(fgs_composite.eiger)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

#     yield from kickoff_and_complete_gridscan(
#         feature_controlled.fgs_motors,
#         fgs_composite.eiger,
#         fgs_composite.synchrotron,
#         [parameters.scan_points_first_grid, parameters.scan_points_second_grid],
#         parameters.scan_indices,
#         plan_during_collection=read_during_collection,
#     )
#     yield from bps.abs_set(feature_controlled.fgs_motors.z_steps, 0, wait=False)


# def wait_for_gridscan_valid(fgs_motors: FastGridScanCommon, timeout=0.5):
#     LOGGER.info("Waiting for valid fgs_params")
#     SLEEP_PER_CHECK = 0.1
#     times_to_check = int(timeout / SLEEP_PER_CHECK)
#     for _ in range(times_to_check):
#         scan_invalid = yield from bps.rd(fgs_motors.scan_invalid)
#         pos_counter = yield from bps.rd(fgs_motors.position_counter)
#         LOGGER.debug(
#             f"Scan invalid: {scan_invalid} and position counter: {pos_counter}"
#         )
#         if not scan_invalid and pos_counter == 0:
#             LOGGER.info("Gridscan scan valid and position counter reset")
#             return
#         yield from bps.sleep(SLEEP_PER_CHECK)
#     raise SampleException("Scan invalid - pin too long/short/bent and out of range")


# def _xrc_result_in_boxes_to_result_in_mm(
#     xrc_result: XrcResult, parameters: SpecifiedThreeDGridScan
# ) -> XRayCentreResult:
#     fgs_params = parameters.FGS_params
#     xray_centre = fgs_params.grid_position_to_motor_position(
#         np.array(xrc_result["centre_of_mass"])
#     )
#     # A correction is applied to the bounding box to map discrete grid coordinates to
#     # the corners of the box in motor-space; we do not apply this correction
#     # to the xray-centre as it is already in continuous space and the conversion has
#     # been performed already
#     # In other words, xrc_result["bounding_box"] contains the position of the box centre,
#     # so we subtract half a box to get the corner of the box
#     return XRayCentreResult(
#         centre_of_mass_mm=xray_centre,
#         bounding_box_mm=(
#             fgs_params.grid_position_to_motor_position(
#                 np.array(xrc_result["bounding_box"][0]) - 0.5
#             ),
#             fgs_params.grid_position_to_motor_position(
#                 np.array(xrc_result["bounding_box"][1]) - 0.5
#             ),
#         ),
#         max_count=xrc_result["max_count"],
#         total_count=xrc_result["total_count"],
#     )
