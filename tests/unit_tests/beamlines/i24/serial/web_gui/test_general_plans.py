from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from dodal.devices.i24.dual_backlight import BacklightPositions

from mx_bluesky.beamlines.i24.serial.parameters.utils import EmptyMapError
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger
from mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans import (
    gui_gonio_move_on_click,
    gui_move_backlight,
    gui_move_detector,
    gui_run_chip_collection,
    gui_stage_move_on_click,
)

from ..conftest import fake_generator


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.caput")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_detector(mock_logger, fake_caput, detector_stage, RE):
    RE(gui_move_detector("eiger", detector_stage))
    fake_caput.assert_called_once_with("BL24I-MO-IOC-13:GP101", "eiger")

    assert await detector_stage.y.user_readback.get_value() == 59.0
    mock_logger.debug.assert_called_once()


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.rd")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.mv")
def test_gui_gonio_move_on_click(fake_mv, fake_rd, RE):
    fake_rd.side_effect = [fake_generator(1.25), fake_generator(1.25)]

    with (
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.oav"),
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.vgonio"),
    ):
        RE(gui_gonio_move_on_click((10, 20)))

    fake_mv.assert_called_with(ANY, 0.0125, ANY, 0.025)


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.get_detector_type")
def test_gui_run_chip_collection_raises_error_for_empty_map(
    mock_det_type,
    RE,
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
):
    mock_det_type.side_effect = [fake_generator(Eiger())]
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
    ]
    with pytest.raises(EmptyMapError):
        RE(
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
def test_gui_stage_move_on_click(fake_move_plan, oav, pmac, RE):
    RE(gui_stage_move_on_click((200, 200), oav, pmac))
    fake_move_plan.assert_called_once_with(oav, pmac, (200, 200))


@pytest.mark.parametrize("position", ["In", "Out", "White In"])
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_backlight(mock_logger, position, backlight, RE):
    RE(gui_move_backlight(position, backlight))

    assert (
        await backlight.backlight_position.pos_level.get_value()
        == BacklightPositions(position)
    )
    mock_logger.debug.assert_called_with(f"Backlight moved to {position}")


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.DCID")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.get_detector_type")
@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._read_visit_directory_from_file"
)
def test_setup_tasks_in_gui_run_chip_collection(
    mock_read_visit,
    mock_det_type,
    mock_dcid,
    RE,
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
    dummy_params_without_pp,
):
    mock_read_visit.return_value = Path("/tmp/dls/i24/fixed/foo")
    mock_det_type.side_effect = [fake_generator(Eiger())]
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
    ]

    expected_params = dummy_params_without_pp
    expected_params.pre_pump_exposure_s = 0.0

    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.run_plan_in_wrapper",
        MagicMock(return_value=iter([])),
    ) as patch_wrapped_plan:
        with patch(
            "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.upload_chip_map_to_geobrick"
        ) as patch_upload:
            RE(
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
