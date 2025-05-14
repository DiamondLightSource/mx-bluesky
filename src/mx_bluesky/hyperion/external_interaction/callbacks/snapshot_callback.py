import dataclasses
import re
from collections.abc import Iterator
from datetime import datetime
from math import cos, radians, sin
from pathlib import Path

from dodal.devices.oav.snapshots.snapshot_image_processing import (
    compute_beam_centre_pixel_xy_for_mm_position,
    draw_crosshair,
)
from event_model import Event, EventDescriptor, RunStart
from PIL import Image

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.parameters.constants import DocDescriptorNames, PlanNameConstants
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER as CALLBACK_LOGGER

COMPRESSION_LEVEL = 6  # 6 is the default compression level for PIL if not specified


@dataclasses.dataclass
class _SnapshotInfo:
    beam_centre: tuple[int, int]
    microns_per_pixel: tuple[float, float]
    snapshot_path: str
    omega: int
    sample_pos_mm: tuple[float, float, float]

    @property
    def snapshot_basename(self) -> str:
        match = re.match("(.*)\\.png", self.snapshot_path)
        assert match, f"Snapshot {self.snapshot_path} was not a .png file"
        return match.groups()[0]


class BeamDrawingCallback(PlanReactiveCallback):
    """
    Callback that monitors for OAV_ROTATION_SNAPSHOT_TRIGGERED events and
    draws a crosshair at the beam centre, saving the snapshot to a file.
    The callback assumes an OAV device "oav" and Smargon "smargon"
    Examples:
        Take a rotation snapshot at the current location
    >>> from bluesky.run_engine import RunEngine
    >>> import bluesky.preprocessors as bpp
    >>> import bluesky.plan_stubs as bps
    >>> from dodal.devices.oav.oav_detector import OAV
    >>> from mx_bluesky.common.parameters.components import WithSnapshot
    >>> def take_snapshot(params: WithSnapshot, oav: OAV, run_engine: RunEngine):
    ...     run_engine.subscribe(BeamDrawingCallback())
    ...     @bpp.run_decorator(md={
    ...     "activate_callbacks": ["BeamDrawingCallback"],
    ...         "with_snapshot": params.model_dump_json(),
    ...     })
    ...     def inner_plan():
    ...         yield from bps.abs_set(oav.snapshot.directory, "/path/to/snapshot_folder", wait=True)
    ...         yield from bps.abs_set(oav.snapshot.filename, "my_snapshot_prefix", wait=True)
    ...         yield from bps.trigger(oav.snapshot, wait=True)
    ...         yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
    ...         yield from bps.read(oav)
    ...         yield from bps.save()

        Generate rotation snapshots from a previously taken base gridscan snapshot.
        WithSnapshot.snapshot_omegas_deg is ignored and snapshots are generated for the previously captured
        0, 90 base images named "my_snapshot_prefix_0" and "my_snapshot_prefix_90"
    >>> from dodal.devices.smargon import Smargon
    >>> def take_snapshot(params: WithSnapshot, oav: OAV, smargon: Smargon, run_engine: RunEngine):
    ...     run_engine.subscribe(BeamDrawingCallback())
    ...     @bpp.run_decorator(md={
    ...     "activate_callbacks": ["BeamDrawingCallback"],
    ...         "with_snapshot": params.model_dump_json(),
    ...     })
    ...     def inner_plan():
    ...         for omega in (0, 90,):
    ...             yield from bps.abs_set(smargon.omega, omega, wait=True)
    ...             yield from bps.abs_set(oav.grid_snapshot.directory, "/path/to/grid_snapshot_folder", wait=True)
    ...             yield from bps.abs_set(oav.grid_snapshot.filename, f"my_grid_snapshot_prefix_{omega}", wait=True)
    ...             yield from bps.trigger(oav.grid_snapshot, wait=True)
    ...             yield from bps.create(DocDescriptorNames.OAV_GRID_SNAPSHOT_TRIGGERED)
    ...             yield from bps.read(oav)        # Capture base image path
    ...             yield from bps.read(smargon)    # Capture base image sample x, y, z, omega
    ...             yield from bps.save()
    ...             # Rest of gridscan here...
    ...         # Later on...
    ...         for omega in (0, 90,):
    ...             yield from bps.abs_set(oav.snapshot.last_saved_path,
    ...                 f"/path/to/snapshot_folder/my_snapshot_prefix_{omega}.png", wait=True)
    ...             yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
    ...             yield from bps.read(oav)            # Capture path info for generated snapshot
    ...             yield from bps.read(smargon)        # Capture the current sample x, y, z
    ...             yield from bps.save()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, log=CALLBACK_LOGGER, **kwargs)
        self._base_snapshots: list[_SnapshotInfo] = []
        self._rotation_snapshot_descriptor: str = ""
        self._grid_snapshot_descriptor: str = ""
        self._next_snapshot_info: Iterator | None = None
        self._use_grid_snapshots: bool = False

    def _reset(self):
        self._base_snapshots = []

    def activity_gated_start(self, doc: RunStart):
        if self.activity_uid == doc.get("uid"):
            self._reset()
            with_snapshot = WithSnapshot.model_validate_json(doc.get("with_snapshot"))  # type: ignore
            self._use_grid_snapshots = with_snapshot.use_grid_snapshots
            CALLBACK_LOGGER.info(f"Snapshot callback initialised with {with_snapshot}")
        elif doc.get("subplan_name") == PlanNameConstants.ROTATION_MAIN:
            self._next_snapshot_info = None
            CALLBACK_LOGGER.info("Snapshot callback start rotation")
        return doc

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        if doc.get("name") == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED:
            self._rotation_snapshot_descriptor = doc["uid"]
        elif doc.get("name") == DocDescriptorNames.OAV_GRID_SNAPSHOT_TRIGGERED:
            self._grid_snapshot_descriptor = doc["uid"]
        return doc

    def activity_gated_event(self, doc: Event) -> Event:
        if doc["descriptor"] == self._rotation_snapshot_descriptor:
            self._handle_rotation_snapshot(doc)
        elif doc["descriptor"] == self._grid_snapshot_descriptor:
            self._handle_grid_snapshot(doc)
        return doc

    def _extract_base_snapshot_params(
        self, snapshot_device_prefix: str, doc: Event
    ) -> _SnapshotInfo:
        data = doc["data"]
        base_snapshot_path = data[f"oav-{snapshot_device_prefix}-last_saved_path"]
        return _SnapshotInfo(
            beam_centre=(data["oav-beam_centre_i"], data["oav-beam_centre_j"]),
            microns_per_pixel=(
                data["oav-microns_per_pixel_x"],
                data["oav-microns_per_pixel_y"],
            ),
            snapshot_path=base_snapshot_path,
            sample_pos_mm=(
                data.get("smargon-x", 0.0),
                data.get("smargon-y", 0.0),
                data.get("smargon-z", 0.0),
            ),
            omega=round(data.get("smargon-omega", 0.0)),
        )

    def _handle_grid_snapshot(self, doc: Event):
        snapshot_info = self._extract_base_snapshot_params("grid_snapshot", doc)
        self._base_snapshots.append(snapshot_info)

    def _handle_rotation_snapshot(self, doc: Event) -> Event:
        data = doc["data"]
        if self._use_grid_snapshots:
            if not self._next_snapshot_info:
                self._next_snapshot_info = iter(self._base_snapshots)
            snapshot_info = next(self._next_snapshot_info, None)
            assert snapshot_info, (
                "Insufficient base gridscan snapshots to generate required rotation snapshots"
            )
            current_sample_pos_mm = (
                data["smargon-x"],
                data["smargon-y"],
                data["smargon-z"],
            )
            CALLBACK_LOGGER.info(
                f"Generating snapshot at {current_sample_pos_mm} from base snapshot {snapshot_info}"
            )
            output_snapshot_directory = data["oav-snapshot-directory"]
            base_file_stem = Path(snapshot_info.snapshot_path).stem
            output_snapshot_filename = _snapshot_filename(base_file_stem)
            output_snapshot_path = (
                f"{output_snapshot_directory}/{output_snapshot_filename}.png"
            )
            self._generate_snapshot_at(
                snapshot_info,
                output_snapshot_path,
                *self._image_plane_offset_mm(snapshot_info, current_sample_pos_mm),
            )
        else:
            snapshot_info = self._extract_base_snapshot_params("snapshot", doc)
            output_snapshot_path = (
                f"{snapshot_info.snapshot_basename}_with_beam_centre.png"
            )
            CALLBACK_LOGGER.info(
                f"Annotating snapshot {output_snapshot_path} from base snapshot {snapshot_info}"
            )
            self._generate_snapshot_zero_offset(
                snapshot_info,
                output_snapshot_path,
            )
        data["oav-snapshot-last_saved_path"] = output_snapshot_path
        return doc

    def _image_plane_offset_mm(
        self,
        snapshot_info: _SnapshotInfo,
        current_sample_pos_mm: tuple[float, float, float],
    ) -> tuple[float, float]:
        return self._project_xyz_to_xy(
            (
                (current_sample_pos_mm[0] - snapshot_info.sample_pos_mm[0]),
                (current_sample_pos_mm[1] - snapshot_info.sample_pos_mm[1]),
                (current_sample_pos_mm[2] - snapshot_info.sample_pos_mm[2]),
            ),
            snapshot_info.omega,
        )

    def _project_xyz_to_xy(
        self, xyz: tuple[float, float, float], omega_deg: float
    ) -> tuple[float, float]:
        return (
            xyz[0],
            xyz[1] * cos(-radians(omega_deg)) + xyz[2] * sin(-radians(omega_deg)),
        )

    def _generate_snapshot_zero_offset(
        self,
        base_snapshot_info: _SnapshotInfo,
        output_snapshot_path: str,
    ):
        self._generate_snapshot_at(base_snapshot_info, output_snapshot_path, 0, 0)

    def _generate_snapshot_at(
        self,
        base_snapshot_info: _SnapshotInfo,
        output_snapshot_path: str,
        image_plane_dx_mm: float,
        image_plane_dy_mm: float,
    ):
        """
        Save a snapshot to the specified path, with an annotated crosshair at the specified
        position
        Args:
            base_snapshot_info: Metadata about the base snapshot image from which the annotated
                image will be derived.
            output_snapshot_path:  The path to the image that will be annotated.
            image_plane_dx_mm: Relative x location of the sample to the original image in the image plane (mm)
            image_plane_dy_mm: Relative y location of the sample to the original image in the image plane (mm)
        """
        image = Image.open(base_snapshot_info.snapshot_path)
        x_px, y_px = compute_beam_centre_pixel_xy_for_mm_position(
            (image_plane_dx_mm, image_plane_dy_mm),
            base_snapshot_info.beam_centre,
            base_snapshot_info.microns_per_pixel,
        )
        draw_crosshair(image, x_px, y_px)
        image.save(output_snapshot_path, format="png", compress_level=COMPRESSION_LEVEL)


def _snapshot_filename(grid_snapshot_name):
    time_now = datetime.now()
    filename = f"{time_now.strftime('%H%M%S%f')[:8]}_oav_snapshot_{grid_snapshot_name}"
    return filename
