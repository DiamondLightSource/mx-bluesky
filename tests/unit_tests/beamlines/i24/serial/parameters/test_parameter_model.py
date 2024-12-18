from pathlib import Path

# import pytest
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.parameters.experiment_parameters import (
    ChipDescription,
    ExtruderParameters,
    FixedTargetParameters,
    SSXType,
)
from mx_bluesky.beamlines.i24.serial.parameters.utils import get_chip_format


def test_extruder_params(dummy_params_ex):
    assert isinstance(dummy_params_ex, ExtruderParameters)
    assert dummy_params_ex.collection_directory == Path("/tmp/dls/i24/extruder/foo/bar")
    assert dummy_params_ex.nexgen_experiment_type == "extruder"
    assert dummy_params_ex.ispyb_experiment_type is SSXType.EXTRUDER


def test_chip_params_with_mapping_lite_and_one_block(dummy_params_without_pp):
    assert isinstance(dummy_params_without_pp, FixedTargetParameters)
    assert dummy_params_without_pp.total_num_images == 400
    assert dummy_params_without_pp.chip.chip_type is ChipType.Oxford
    assert dummy_params_without_pp.nexgen_experiment_type == "fixed-target"
    assert dummy_params_without_pp.ispyb_experiment_type is SSXType.FIXED


def test_chip_params_with_multiple_blocks(dummy_params_without_pp):
    dummy_params_without_pp.chip_map = [1, 2, 3]
    assert dummy_params_without_pp.total_num_images == 1200
    assert dummy_params_without_pp.map_type is MappingType.Lite
    assert dummy_params_without_pp.pump_repeat is PumpProbeSetting.NoPP


def test_chip_params_with_multiple_exposures(dummy_params_without_pp):
    dummy_params_without_pp.num_exposures = 2
    dummy_params_without_pp.chip_map = [1, 16]
    assert dummy_params_without_pp.total_num_images == 1600


def test_chip_params_with_no_mapping_for_oxford_chip():
    oxford_defaults = get_chip_format(ChipType.Oxford)
    oxford_chip = {
        "visit": "foo",
        "directory": "bar",
        "filename": "chip",
        "exposure_time_s": 0.01,
        "detector_distance_mm": 100,
        "detector_name": "eiger",
        "transmission": 1.0,
        "num_exposures": 1,
        "chip": oxford_defaults.model_dump(),
        "map_type": 0,
        "pump_repeat": 0,
        "checker_pattern": False,
        "chip_map": [],
    }
    params = FixedTargetParameters(**oxford_chip)
    assert params.total_num_images == 25600


def test_chip_params_with_no_mapping_for_custom_chip():
    custom_defaults = {
        "chip_type": ChipType.Custom,
        "x_num_steps": 5,
        "y_num_steps": 3,
        "x_step_size": 0.1,
        "y_step_size": 0.1,
        "x_blocks": 1,
        "y_blocks": 1,
        "b2b_horz": 0.0,
        "b2b_vert": 0.0,
    }
    custom_chip = {
        "visit": "foo",
        "directory": "bar",
        "filename": "chip",
        "exposure_time_s": 0.01,
        "detector_distance_mm": 100,
        "detector_name": "eiger",
        "transmission": 1.0,
        "num_exposures": 2,
        "chip": ChipDescription(**custom_defaults),
        "map_type": 0,
        "pump_repeat": 0,
        "checker_pattern": False,
        "chip_map": [],
    }
    params = FixedTargetParameters(**custom_chip)
    assert params.total_num_images == 30
