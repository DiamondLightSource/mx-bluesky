from typing import Generic, TypedDict, TypeVar

import numpy as np
from bluesky.callbacks import CallbackBase
from dodal.devices.oav.utils import calculate_x_y_z_of_pixel
from event_model.documents import Event

from mx_bluesky.common.utils.log import LOGGER

T = TypeVar("T", int, float)


class GridParamUpdate(TypedDict):
    """
    Grid parameters extracted from the grid detection.
    Positions are in motor-space.

    Attributes:
        x_start_um: x position of the centre of the first xy-gridscan box in microns
        y_start_um: y position of the centre of the first xy-gridscan box in microns
        y2_start_um: y position of the centre of the first xz-gridscan box in microns
        z_start_um: z position of the centre of the first xy-gridscan box in microns
        z2_start_um: z position of the centre of the first xz-gridscan box in microns
        x_steps: Number of grid boxes in x-direction for xy- and xz- gridscans
        y_steps: Number of grid boxes in y-direction for xy-gridscan
        z_steps: Number of grid boxes in z-direction for xz-gridscan
        x_step_size_um: x-dimension of the grid box
        y_step_size_um: y-dimension of the grid box
        z_step_size_um: z-dimension of the grid box
    """

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


class XYZParams(TypedDict, Generic[T]):
    x: T
    y: T
    z: T


class GridDetectionCallback(CallbackBase):
    OMEGA_TOLERANCE = 1

    def __init__(
        self,
        *args,
    ) -> None:
        super().__init__(*args)
        self.start_positions_um: XYZParams[float] = XYZParams(x=0, y=0, z=0)
        self.box_numbers: XYZParams[int] = XYZParams(x=0, y=0, z=0)

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

        # If data is taken at omega=~0 then it gives us x-y info, at omega=~-90 it is x-z
        if abs(smargon_omega) < self.OMEGA_TOLERANCE:
            self.start_positions_um["x"] = position_grid_start_mm[0] * 1000
            self.start_positions_um["y"] = position_grid_start_mm[1] * 1000
            self.box_numbers["x"] = data["oav-grid_snapshot-num_boxes_x"]
            self.box_numbers["y"] = data["oav-grid_snapshot-num_boxes_y"]
        elif abs(smargon_omega + 90) < self.OMEGA_TOLERANCE:
            self.start_positions_um["x"] = position_grid_start_mm[0] * 1000
            self.start_positions_um["z"] = position_grid_start_mm[2] * 1000
            self.box_numbers["x"] = data["oav-grid_snapshot-num_boxes_x"]
            self.box_numbers["z"] = data["oav-grid_snapshot-num_boxes_y"]
        else:
            raise ValueError(
                f"Grid detection only works at omegas of 0 or -90, omega of {smargon_omega} given."
            )

        self.x_step_size_um = box_width_px * microns_per_pixel_x
        self.y_step_size_um = box_width_px * microns_per_pixel_y
        self.z_step_size_um = box_width_px * microns_per_pixel_y
        return doc

    def get_grid_parameters(self) -> GridParamUpdate:
        return {
            "x_start_um": self.start_positions_um["x"],
            "y_start_um": self.start_positions_um["y"],
            "y2_start_um": self.start_positions_um["y"],
            "z_start_um": self.start_positions_um["z"],
            "z2_start_um": self.start_positions_um["z"],
            "x_steps": self.box_numbers["x"],
            "y_steps": self.box_numbers["y"],
            "z_steps": self.box_numbers["z"],
            "x_step_size_um": self.x_step_size_um,
            "y_step_size_um": self.y_step_size_um,
            "z_step_size_um": self.z_step_size_um,
        }
