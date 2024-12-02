from typing import TypedDict

import numpy as np
from bluesky.callbacks import CallbackBase
from dodal.devices.oav.utils import calculate_x_y_z_of_pixel
from event_model.documents import Event

from mx_bluesky.hyperion.log import LOGGER


class GridParamUpdate(TypedDict):
    x_start_um: float
    y_start_um: float
    y2_start_um: float
    z_start_um: float
    z2_start_um: float
    x_steps: int
    y_steps: int
    z_steps: int
    x_step_size_um: float
    y_step_size_um: float
    z_step_size_um: float


class GridDetectionCallback(CallbackBase):
    def __init__(
        self,
        *args,
    ) -> None:
        super().__init__(*args)
        self.start_positions_mm: list = []
        self.box_numbers: list = []

    def event(self, doc: Event):
        data = doc.get("data")
        top_left_x_px = data["oav-grid_snapshot-top_left_x"]
        box_width_px = data["oav-grid_snapshot-box_width"]
        x_of_centre_of_first_box_px = top_left_x_px + box_width_px / 2

        top_left_y_px = data["oav-grid_snapshot-top_left_y"]
        y_of_centre_of_first_box_px = top_left_y_px + box_width_px / 2

        smargon_omega = data["smargon-omega"]
        current_xyz = np.array(
            [data["smargon-x"], data["smargon-y"], data["smargon-z"]]
        )

        centre_of_first_box = (
            x_of_centre_of_first_box_px,
            y_of_centre_of_first_box_px,
        )

        microns_per_pixel_x = data["oav-microns_per_pixel_x"]
        microns_per_pixel_y = data["oav-microns_per_pixel_y"]
        beam_x = data["oav-beam_centre_i"]
        beam_y = data["oav-beam_centre_j"]

        position_grid_start_mm = calculate_x_y_z_of_pixel(
            current_xyz,
            smargon_omega,
            centre_of_first_box,
            (beam_x, beam_y),
            (microns_per_pixel_x, microns_per_pixel_y),
        )
        LOGGER.info(f"Calculated start position {position_grid_start_mm}")

        self.start_positions_mm.append(position_grid_start_mm)
        self.box_numbers.append(
            (
                data["oav-grid_snapshot-num_boxes_x"],
                data["oav-grid_snapshot-num_boxes_y"],
            )
        )

        self.x_step_size_um = box_width_px * microns_per_pixel_x
        self.y_step_size_um = box_width_px * microns_per_pixel_y
        self.z_step_size_um = box_width_px * microns_per_pixel_y
        return doc

    def get_grid_parameters(self) -> GridParamUpdate:
        return {
            "x_start_um": self.start_positions_mm[0][0] * 1000,
            "y_start_um": self.start_positions_mm[0][1] * 1000,
            "y2_start_um": self.start_positions_mm[0][1] * 1000,
            "z_start_um": self.start_positions_mm[1][2] * 1000,
            "z2_start_um": self.start_positions_mm[1][2] * 1000,
            "x_steps": self.box_numbers[0][0],
            "y_steps": self.box_numbers[0][1],
            "z_steps": self.box_numbers[1][1],
            "x_step_size_um": self.x_step_size_um,
            "y_step_size_um": self.y_step_size_um,
            "z_step_size_um": self.z_step_size_um,
        }
