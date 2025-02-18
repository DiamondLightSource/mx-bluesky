from dataclasses import asdict, dataclass
from enum import Enum


class Orientation(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass()
class DataCollectionGroupInfo:
    visit_string: str
    experiment_type: str
    sample_id: int | None
    sample_barcode: str | None = None
    comments: str | None = None


@dataclass(kw_only=True)
class DataCollectionInfo:
    omega_start: float | None = None
    data_collection_number: int | None = None
    xtal_snapshot1: str | None = None
    xtal_snapshot2: str | None = None
    xtal_snapshot3: str | None = None
    xtal_snapshot4: str | None = None

    n_images: int | None = None
    axis_range: float | None = None
    axis_end: float | None = None
    kappa_start: float | None = None

    parent_id: int | None = None
    visit_string: str | None = None
    sample_id: int | None = None
    detector_id: int | None = None
    axis_start: float | None = None
    focal_spot_size_at_samplex: float | None = None
    focal_spot_size_at_sampley: float | None = None
    slitgap_vertical: float | None = None
    slitgap_horizontal: float | None = None
    beamsize_at_samplex: float | None = None
    beamsize_at_sampley: float | None = None
    transmission: float | None = None
    comments: str | None = None
    detector_distance: float | None = None
    exp_time: float | None = None
    imgdir: str | None = None
    file_template: str | None = None
    imgprefix: str | None = None
    imgsuffix: str | None = None
    n_passes: int | None = None
    overlap: int | None = None
    flux: float | None = None
    start_image_number: int | None = None
    resolution: float | None = None
    wavelength: float | None = None
    xbeam: float | None = None
    ybeam: float | None = None
    synchrotron_mode: str | None = None
    undulator_gap1: float | None = None
    start_time: str | None = None


@dataclass
class DataCollectionPositionInfo:
    pos_x: float
    pos_y: float
    pos_z: float


@dataclass
class DataCollectionGridInfo:
    """This information is used by Zocalo gridscan per-image-analysis"""

    dx_in_mm: float
    dy_in_mm: float
    steps_x: int
    steps_y: int
    microns_per_pixel_x: float
    microns_per_pixel_y: float
    snapshot_offset_x_pixel: int
    snapshot_offset_y_pixel: int
    orientation: Orientation
    snaked: bool

    def as_dict(self):
        d = asdict(self)
        d["orientation"] = self.orientation.value
        return d


@dataclass(kw_only=True)
class ScanDataInfo:
    data_collection_info: DataCollectionInfo
    data_collection_id: int | None = None
    data_collection_position_info: DataCollectionPositionInfo | None = None
    data_collection_grid_info: DataCollectionGridInfo | None = None
