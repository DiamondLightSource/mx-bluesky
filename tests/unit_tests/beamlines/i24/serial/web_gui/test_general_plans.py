from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.i24.dual_backlight import BacklightPositions

from mx_bluesky.beamlines.i24.serial.parameters.utils import EmptyMapError
from mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans import (
    gui_gonio_move_on_click,
    gui_move_backlight,
    gui_move_detector,
    gui_run_chip_collection,
    gui_run_extruder_collection,
    gui_set_fiducial_0,
    gui_stage_move_on_click,
)

from ..conftest import fake_generator


@pytest.fixture
def enum_attenuator(run_engine) -> EnumFilterAttenuator:
    attenuator: EnumFilterAttenuator = i24.attenuator(
        connect_immediately=True, mock=True
    )
    # set_mock_value(attenuator.actual_transmission, 1.0)
    return attenuator


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.caput")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_detector(mock_logger, fake_caput, detector_stage, run_engine):
    run_engine(gui_move_detector("eiger", detector_stage))
    fake_caput.assert_called_once_with("BL24I-MO-IOC-13:GP101", "eiger")

    assert await detector_stage.y.user_readback.get_value() == 59.0
    mock_logger.debug.assert_called_once()


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.rd")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.mv")
def test_gui_gonio_move_on_click(fake_mv, fake_rd, run_engine):
    fake_rd.side_effect = [fake_generator(1.25), fake_generator(1.25)]

    with (
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.oav"),
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.vgonio"),
    ):
        run_engine(gui_gonio_move_on_click((10, 20)))

    fake_mv.assert_called_with(ANY, 0.0125, ANY, 0.025)


def test_gui_run_chip_collection_raises_error_for_empty_map(
    run_engine,
    pmac,
    zebra,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    shutter,
    dcm,
    mirrors,
    eiger_beam_center,
    enum_attenuator,
):
    device_list = [
        pmac,
        zebra,
        aperture,
        backlight,
        beamstop,
        detector_stage,
        shutter,
        dcm,
        mirrors,
        eiger_beam_center,
        enum_attenuator,
    ]
    with pytest.raises(EmptyMapError):
        run_engine(
            gui_run_chip_collection(
                "/path/",
                "chip",
                0.01,
                1300,
                0.3,
                1,
                "Oxford",
                "Lite",
                [],
                False,
                "Short1",
                0.01,
                0.005,
                0.0,
                *device_list,
            )
        )


@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._move_on_mouse_click_plan"
)
def test_gui_stage_move_on_click(fake_move_plan, oav, pmac, run_engine):
    run_engine(gui_stage_move_on_click((200, 200), oav, pmac))
    fake_move_plan.assert_called_once_with(oav, pmac, (200, 200))


@pytest.mark.parametrize("position", ["In", "Out", "White In"])
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_backlight(mock_logger, position, backlight, run_engine):
    run_engine(gui_move_backlight(position, backlight))

    assert (
        await backlight.backlight_position.pos_level.get_value()
        == BacklightPositions(position)
    )
    mock_logger.debug.assert_called_with(f"Backlight moved to {position}")


async def test_gui_set_fiducial_0(pmac, run_engine):
    run_engine(gui_set_fiducial_0(pmac))

    assert await pmac.pmac_string.get_value() == r"&2\#5hmz\#6hmz\#7hmz"


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._read_visit_directory_from_file"
)
def test_setup_tasks_in_gui_run_chip_collection(
    mock_read_visit,
    mock_dcid,
    run_engine,
    pmac,
    zebra,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    shutter,
    dcm,
    mirrors,
    eiger_beam_center,
    enum_attenuator,
    dummy_params_without_pp,
):
    mock_read_visit.return_value = Path("/tmp/dls/i24/fixed/foo")
    device_list = [
        pmac,
        zebra,
        aperture,
        backlight,
        beamstop,
        detector_stage,
        shutter,
        dcm,
        mirrors,
        eiger_beam_center,
        enum_attenuator,
    ]

    expected_params = dummy_params_without_pp
    expected_params.pre_pump_exposure_s = 0.0

    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.run_ft_collection_plan",
        MagicMock(return_value=iter([])),
    ) as patch_wrapped_plan:
        with (
            patch(
                "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.upload_chip_map_to_geobrick"
            ) as patch_upload,
            patch(
                "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.abs_set"
            ) as patch_set,
        ):
            run_engine(
                gui_run_chip_collection(
                    "bar",
                    "chip",
                    0.01,
                    100,
                    1.0,
                    1,
                    "Oxford",
                    "Lite",
                    [1],
                    False,
                    "NoPP",
                    0.0,
                    0.0,
                    0.0,
                    *device_list,
                )
            )

            patch_upload.assert_called_once_with(pmac, [1])
            patch_set.assert_called_once_with(enum_attenuator, 1.0, wait=True)
            mock_dcid.assert_called_once()
            patch_wrapped_plan.assert_called_once_with(
                zebra,
                pmac,
                aperture,
                backlight,
                beamstop,
                detector_stage,
                shutter,
                dcm,
                mirrors,
                eiger_beam_center,
                expected_params,
                mock_dcid(),
            )


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._read_visit_directory_from_file"
)
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.datetime")
def test_gui_run_extruder_collection(
    mock_datetime,
    mock_read_visit,
    mock_dcid,
    run_engine,
    dummy_params_ex,
    zebra,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    shutter,
    dcm,
    mirrors,
    enum_attenuator,
    eiger_beam_center,
):
    fake_start = datetime.now()
    mock_datetime.now.return_value = fake_start
    mock_read_visit.return_value = Path("/tmp/dls/i24/extruder/foo")

    device_list = [
        zebra,
        aperture,
        backlight,
        beamstop,
        detector_stage,
        shutter,
        dcm,
        mirrors,
        enum_attenuator,
        eiger_beam_center,
    ]

    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.run_ex_collection_plan",
        MagicMock(return_value=iter([])),
    ) as patch_wrapped_plan:
        with patch(
            "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.abs_set"
        ) as patch_set:
            run_engine(
                gui_run_extruder_collection(
                    "bar", "protein", 0.1, 100, 1.0, 10, False, 0.0, 0.0, *device_list
                )
            )

            patch_set.assert_called_once_with(enum_attenuator, 1.0, wait=True)
            mock_dcid.assert_called_once()
            patch_wrapped_plan.assert_called_once_with(
                zebra,
                aperture,
                backlight,
                beamstop,
                detector_stage,
                shutter,
                dcm,
                mirrors,
                eiger_beam_center,
                dummy_params_ex,
                mock_dcid(),
                fake_start,
            )
