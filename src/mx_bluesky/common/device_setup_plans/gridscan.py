from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.fast_grid_scan import (
    FastGridScanThreeD,
    ZebraGridScanParamsThreeD,
    set_fast_grid_scan_params,
)
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import (
    MXZebraShutter,
    ZebraShutterControl,
)

from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    configure_zebra_and_shutter_for_auto_shutter,
    set_shutter_auto_input,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    TSetupParameters,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.constants import ZEBRA_STATUS_TIMEOUT
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.utils.log import LOGGER


@runtime_checkable
class GridscanSetupDevices(Protocol):
    zebra: Zebra
    sample_shutter: MXZebraShutter


TZebraGridscanDevices = TypeVar("TZebraGridscanDevices", bound=GridscanSetupDevices)


def set_zebra_fgs_3d_params(
    fast_grid_scan: FastGridScanThreeD[ZebraGridScanParamsThreeD],
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    set_stub_offsets: bool = False,
) -> MsgGenerator:
    zebra_fgs_params = _fast_gridscan_3d_params(
        expt_params, grid_scan_params, set_stub_offsets
    )
    yield from set_fast_grid_scan_params(fast_grid_scan, zebra_fgs_params)


def _fast_gridscan_3d_params(
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    set_stub_offsets: bool,
) -> ZebraGridScanParamsThreeD:
    """During 3D grid scans, there is an omega rotation before the second grid,
    transforming Y -> Z axes, so use the second element of the Y params to set
    Z params on the 3D grid scan device.
    """
    return ZebraGridScanParamsThreeD(
        x_steps=grid_scan_params.x_steps,
        y_steps=grid_scan_params.y_steps[0],
        z_steps=grid_scan_params.y_steps[1],
        x_step_size_mm=grid_scan_params.x_step_size_um / 1000,
        y_step_size_mm=grid_scan_params.y_step_sizes_um[0] / 1000,
        z_step_size_mm=grid_scan_params.y_step_sizes_um[1] / 1000,
        x_start_mm=grid_scan_params.x_start_um / 1000,
        y1_start_mm=grid_scan_params.y_starts_um[0] / 1000,
        z1_start_mm=grid_scan_params.z_starts_um[0] / 1000,
        y2_start_mm=grid_scan_params.y_starts_um[1] / 1000,
        z2_start_mm=grid_scan_params.z_starts_um[1] / 1000,
        set_stub_offsets=set_stub_offsets,
        dwell_time_ms=expt_params.exposure_time_s * 1000,
        transmission_fraction=expt_params.transmission_frac,
    )


def tidy_up_zebra_after_gridscan(
    zebra: Zebra,
    zebra_shutter: MXZebraShutter,
    group="tidy_up_zebra_after_gridscan",
    wait=True,
    ttl_input_for_detector_to_use: int | None = None,
) -> MsgGenerator:
    """
    Set the zebra back to a state which is expected by GDA.

    Args:
        zebra: Zebra device.
        zebra_shutter: Zebra shutter device.
        group: Bluesky group to use when waiting on completion.
        wait: If true, block until completion.
        ttl_input_for_detector_to_use: If the zebra isn't using the TTL_DETECTOR zebra input, manually
        specify which TTL input is being used for the desired detector.
    """

    LOGGER.info("Tidying up Zebra")

    ttl_detector = ttl_input_for_detector_to_use or zebra.mapping.outputs.TTL_DETECTOR

    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    yield from set_shutter_auto_input(zebra, zebra.mapping.sources.PC_GATE, group=group)

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def setup_zebra_for_gridscan(
    composite: TZebraGridscanDevices,  # type: ignore
    _: TSetupParameters,  # type: ignore
    __: GridScanParams,
) -> MsgGenerator:
    yield from _setup_zebra_for_gridscan(composite)


def _setup_zebra_for_gridscan(
    composite: GridscanSetupDevices,  # XRC gridscan's generic trigger setup expects a composite rather than individual devices
    group="setup_zebra_for_gridscan",
    wait=True,
    ttl_input_for_detector_to_use: None | int = None,
) -> MsgGenerator:
    """
    Configure the zebra for an MX XRC gridscan by allowing the zebra to trigger the fast shutter and detector via signals
    sent from the motion controller.

    Args:
        composite: Composite device containing a zebra and zebra shutter
        group: Bluesky group to use when waiting on completion
        wait: If true, block until completion
        ttl_input_for_detector_to_use: If the zebra isn't using the TTL_DETECTOR zebra input, manually
        specify which TTL input is being used for the desired detector

    This plan assumes that the motion controller, as part of its gridscan PLC, will send triggers as required to the zebra's
    IN4_TTL and IN3_TTL to control the fast_shutter and detector respectively

    """
    zebra = composite.zebra
    ttl_detector = ttl_input_for_detector_to_use or zebra.mapping.outputs.TTL_DETECTOR
    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, composite.sample_shutter, zebra.mapping.sources.IN4_TTL, group=group
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.IN3_TTL,
        group=group,
    )

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
