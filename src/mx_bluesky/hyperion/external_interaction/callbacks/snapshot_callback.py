from dodal.devices.oav.snapshots.snapshot_image_processing import (
    compute_beam_centre_pixel_xy_for_mm_position,
    draw_crosshair,
)
from event_model import Event, EventDescriptor, RunStart
from PIL import Image

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.parameters.components import (
    WithSnapshot,
)
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER as CALLBACK_LOGGER


class BeamDrawingCallback(PlanReactiveCallback):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, log=CALLBACK_LOGGER, **kwargs)
        self._rotation_snapshot_descriptor: None
        self._snapshot_files: list[str] = []
        self._microns_per_pixel: tuple[float, float]
        self._beam_centre: tuple[int, int]
        self._rotation_snapshot_descriptor: str = ""

    def activity_gated_start(self, doc: RunStart):
        if self.activity_uid == doc.get("uid"):
            params = WithSnapshot.model_validate_json(doc.get("with_snapshot"))
            self._output_directory = params.snapshot_directory
        return doc

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        if doc["name"] == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED:
            self._rotation_snapshot_descriptor = doc["uid"]
        return doc

    def activity_gated_event(self, doc: Event) -> Event:
        if doc["descriptor"] == self._rotation_snapshot_descriptor:
            self._handle_rotation_snapshot(doc)
        return doc

    def _extract_base_snapshot_params(self, doc: Event):
        data = doc["data"]
        self._snapshot_files.append(data["oav-snapshot-last_saved_path"])
        self._microns_per_pixel = (
            data["oav-microns_per_pixel_x"],
            data["oav-microns_per_pixel_y"],
        )
        self._beam_centre = (data["oav-beam_centre_i"], data["oav-beam_centre_j"])

    def _handle_rotation_snapshot(self, doc: Event):
        self._extract_base_snapshot_params(doc)
        data = doc["data"]
        snapshot_path = data["oav-snapshot-last_saved_path"]
        self._generate_snapshot_at(snapshot_path, snapshot_path, 0, 0)
        return doc

    def _generate_snapshot_at(
        self, input_snapshot_path: str, output_snapshot_path: str, x_mm: int, y_mm: int
    ):
        image = Image.open(input_snapshot_path)
        x_px, y_px = compute_beam_centre_pixel_xy_for_mm_position(
            (x_mm, y_mm), self._beam_centre, self._microns_per_pixel
        )
        draw_crosshair(image, x_px, y_px)
        image.save(output_snapshot_path, format="png")
