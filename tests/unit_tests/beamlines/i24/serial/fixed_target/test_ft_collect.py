import asyncio
from datetime import datetime
from unittest.mock import ANY, MagicMock, call, mock_open, patch

import pytest
from bluesky.utils import FailedStatus
from dodal.devices.hutch_shutter import HutchShutter
from dodal.devices.i24.pmac import PMAC
from dodal.devices.zebra.zebra import Zebra
from ophyd_async.testing import callback_on_mock_put, get_mock_put, set_mock_value

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1 import (
    finish_i24,
    get_chip_prog_values,
    get_prog_num,
    kickoff_and_complete_collection,
    load_motion_program_data,
    main_fixed_target_plan,
    run_aborted_plan,
    run_fixed_target_plan,
    set_datasize,
    start_i24,
    tidy_up_after_collection_plan,
    write_userlog,
)
from mx_bluesky.beamlines.i24.serial.parameters.experiment_parameters import (
    BeamSettings,
)

from ..conftest import TEST_LUT, fake_generator

chipmap_str = """01status    P3011       1
02status    P3021       0
03status    P3031       0
04status    P3041       0"""


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.SSX_LOGGER"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.Path.mkdir"
)
def test_write_userlog(fake_mkdir, fake_log, dummy_params_without_pp):
    with patch(
        "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.open",
        mock_open(),
    ):
        write_userlog(dummy_params_without_pp, "some_file", 1.0, 0.6)
    fake_log.debug.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.SSX_LOGGER"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.caput")
def test_set_datasize_for_one_block_and_two_exposures(
    fake_caput, fake_log, dummy_params_without_pp
):
    dummy_params_without_pp.num_exposures = 2
    dummy_params_without_pp.chip_map = [20]
    assert dummy_params_without_pp.total_num_images == 800
    set_datasize(dummy_params_without_pp)
    fake_caput.assert_called_once_with("ME14E-MO-IOC-01:GP10", 800)
    assert fake_log.info.call_count == 1
    assert fake_log.debug.call_count == 4


def test_get_chip_prog_values(dummy_params_without_pp):
    dummy_params_without_pp.num_exposures = 2
    chip_dict = get_chip_prog_values(
        dummy_params_without_pp,
    )
    assert isinstance(chip_dict, dict)
    assert chip_dict["X_NUM_STEPS"][1] == 20 and chip_dict["X_NUM_BLOCKS"][1] == 8
    assert chip_dict["PUMP_REPEAT"][1] == 0
    assert chip_dict["N_EXPOSURES"][1] == 2


@pytest.mark.parametrize(
    "chip_type, map_type, pump_repeat, expected_prog",
    [
        (ChipType.Oxford, MappingType.NoMap, PumpProbeSetting.NoPP, 11),
        (ChipType.Oxford, MappingType.Lite, PumpProbeSetting.NoPP, 12),
        (ChipType.OxfordInner, MappingType.Lite, PumpProbeSetting.NoPP, 12),
        (ChipType.Custom, MappingType.Lite, PumpProbeSetting.NoPP, 11),
        (ChipType.Minichip, MappingType.NoMap, PumpProbeSetting.NoPP, 11),
        (ChipType.Oxford, MappingType.Lite, PumpProbeSetting.Short2, 14),
        (ChipType.Minichip, MappingType.NoMap, PumpProbeSetting.Repeat5, 14),
        (ChipType.Custom, MappingType.Lite, PumpProbeSetting.Medium1, 14),
    ],
)
def test_get_prog_number(chip_type, map_type, pump_repeat, expected_prog):
    assert get_prog_num(chip_type, map_type, pump_repeat) == expected_prog


@pytest.mark.parametrize(
    "map_type, pump_repeat, checker, expected_calls",
    [
        (0, 0, False, ["P1100=1"]),  # Full chip, no pump probe, no checker
        (1, 0, False, ["P1200=1"]),  # Mapping lite, no pp, no checker
        (
            1,
            2,
            False,
            ["P1439=0", "P1441=0", "P1400=1"],
        ),  # Map irrelevant, pp to Repeat1, no checker
        (
            0,
            3,
            True,
            ["P1439=0", "P1439=1", "P1441=0", "P1400=1"],
        ),  # Map irrelevant, pp to Repeat2, checker enabled
        (
            1,
            8,
            False,
            ["P1439=0", "P1441=50", "P1400=1"],
        ),  # Map irrelevant, pp to Medium1, checker disabled
    ],
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
def test_load_motion_program_data(
    mock_sleep,
    map_type: int,
    pump_repeat: int,
    checker: bool,
    expected_calls: list,
    pmac: PMAC,
    RE,
):
    test_dict = {"N_EXPOSURES": [0, 1]}
    RE(load_motion_program_data(pmac, test_dict, map_type, pump_repeat, checker))
    call_list = []
    for i in expected_calls:
        call_list.append(call(i, wait=True))
    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_pmac_str.assert_has_calls(call_list)


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.DCID")
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.caput")
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.cagetstring"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.sup")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.datetime"
)
def test_start_i24_with_eiger(
    fake_datetime,
    fake_sleep,
    fake_sup,
    fake_cagetstring,
    fake_caget,
    fake_caput,
    fake_dcid,
    zebra: Zebra,
    shutter: HutchShutter,
    RE,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    dcm,
    mirrors,
    eiger_beam_center,
    dummy_params_without_pp,
):
    expected_start = datetime.now()
    fake_datetime.now.return_value = expected_start
    dummy_params_without_pp.chip_map = [1, 2]
    assert dummy_params_without_pp.total_num_images == 800
    set_mock_value(dcm.wavelength_in_a.user_readback, 0.6)
    expected_beam_settings = BeamSettings(
        wavelength_in_a=0.6,
        beam_size_in_um=(7.0, 7.0),
        beam_center_in_mm=(1605 * 0.075, 1702 * 0.075),
    )
    expected_odin_filename = f"{dummy_params_without_pp.filename}_0001"
    fake_cagetstring.return_value = expected_odin_filename

    RE(
        start_i24(
            zebra,
            aperture,
            backlight,
            beamstop,
            detector_stage,
            shutter,
            dummy_params_without_pp,
            dcm,
            mirrors,
            eiger_beam_center,
            fake_dcid,
        )
    )
    assert fake_sup.eiger.call_count == 1
    assert fake_sup.setup_beamline_for_collection_plan.call_count == 1
    assert fake_sup.move_detector_stage_to_position_plan.call_count == 1
    fake_cagetstring.assert_called_once()
    fake_dcid.generate_dcid.assert_called_with(
        beam_settings=expected_beam_settings,
        image_dir=dummy_params_without_pp.collection_directory.as_posix(),
        file_template=f"{expected_odin_filename}.nxs",
        num_images=dummy_params_without_pp.total_num_images,
        shots_per_position=dummy_params_without_pp.num_exposures,
        start_time=expected_start,
        pump_probe=False,
    )

    shutter_call_list = [
        call("Reset", wait=True),
        call("Open", wait=True),
    ]
    mock_shutter = get_mock_put(shutter.control)
    mock_shutter.assert_has_calls(shutter_call_list)


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.write_userlog"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.cagetstring"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.caget")
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.sup")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.reset_zebra_when_collection_done_plan"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.rd")
def test_finish_i24(
    fake_read,
    fake_reset_zebra,
    fake_sup,
    fake_caget,
    fake_cagetstring,
    fake_sleep,
    fake_userlog,
    zebra,
    pmac,
    shutter,
    dcm,
    dummy_params_without_pp,
    RE,
):
    fake_read.side_effect = [fake_generator(0.6)]
    fake_caget.return_value = 0.0
    fake_cagetstring.return_value = "chip_01"
    RE(finish_i24(zebra, pmac, shutter, dcm, dummy_params_without_pp))

    fake_reset_zebra.assert_called_once()

    fake_sup.eiger.assert_called_once_with("return-to-normal", None, dcm)

    mock_pmac_string = get_mock_put(pmac.pmac_string)
    mock_pmac_string.assert_has_calls([call("!x0y0z0", wait=True)])

    mock_shutter = get_mock_put(shutter.control)
    mock_shutter.assert_has_calls([call("Close", wait=True)])

    fake_userlog.assert_called_once_with(dummy_params_without_pp, "chip_01", 0.0, 0.6)


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.SSX_LOGGER"
)
def test_run_aborted_plan(
    mock_log: MagicMock, fake_dcid: MagicMock, pmac: PMAC, RE, done_status
):
    pmac.abort_program.trigger = MagicMock(return_value=done_status)
    RE(run_aborted_plan(pmac, fake_dcid, Exception("Test Exception")))

    pmac.abort_program.trigger.assert_called_once()
    fake_dcid.collection_complete.assert_called_once_with(ANY, aborted=True)
    assert "Test Exception" in mock_log.warning.mock_calls[0].args[0]


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.finish_i24"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.DCID")
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.caput")
async def test_tidy_up_after_collection_plan(
    fake_caput,
    fake_dcid,
    fake_sleep,
    mock_finish,
    zebra,
    pmac,
    shutter,
    dcm,
    RE,
    dummy_params_without_pp,
):
    RE(
        tidy_up_after_collection_plan(
            zebra, pmac, shutter, dcm, dummy_params_without_pp, fake_dcid
        )
    )
    assert await zebra.inputs.soft_in_2.get_value() == "No"

    fake_dcid.notify_end.assert_called_once()

    fake_caput.assert_has_calls([call(ANY, 0), call(ANY, "Done")])

    mock_finish.assert_called_once()


async def test_kick_off_and_complete_collection(
    pmac, dummy_params_with_pp, RE, done_status
):
    pmac.run_program.kickoff = MagicMock(return_value=done_status)
    pmac.run_program.complete = MagicMock(return_value=done_status)

    async def go_high_then_low():
        set_mock_value(pmac.scanstatus, 1)
        await asyncio.sleep(0.1)
        set_mock_value(pmac.scanstatus, 0)

    callback_on_mock_put(
        pmac.pmac_string,
        lambda *args, **kwargs: asyncio.create_task(go_high_then_low()),  # type: ignore
    )
    res = RE(kickoff_and_complete_collection(pmac, dummy_params_with_pp))

    assert await pmac.program_number.get_value() == 14

    pmac.run_program.kickoff.assert_called_once()
    pmac.run_program.complete.assert_called_once()

    assert res.exit_status == "success"


@patch("dodal.devices.i24.pmac.DEFAULT_TIMEOUT", 0.1)
async def test_kickoff_and_complete_fails_if_scan_status_pv_does_not_change(
    pmac, dummy_params_without_pp, RE
):
    pmac.run_program.KICKOFF_TIMEOUT = 0.1
    set_mock_value(pmac.scanstatus, 0)
    with pytest.raises(FailedStatus):
        RE(kickoff_and_complete_collection(pmac, dummy_params_without_pp))


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.kickoff_and_complete_collection"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.start_i24"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.set_datasize"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.load_motion_program_data"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.get_chip_prog_values"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.call_nexgen"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
async def test_main_fixed_target_plan(
    fake_sleep,
    fake_nexgen,
    fake_dcid,
    mock_get_chip_prog,
    mock_motion_program,
    fake_datasize,
    mock_start,
    mock_kickoff,
    RE,
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
    dummy_params_without_pp,
):
    mock_get_chip_prog.return_value = MagicMock()
    set_mock_value(dcm.wavelength_in_a.user_readback, 0.6)
    fake_datasize.return_value = 400
    with patch(
        "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.BEAM_CENTER_LUT_FILES",
        new=TEST_LUT,
    ):
        with patch(
            "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
        ):
            RE(
                main_fixed_target_plan(
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
                    dummy_params_without_pp,
                    fake_dcid,
                )
            )

    mock_beam_x = get_mock_put(eiger_beam_center.beam_x)
    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_zebra_input = get_mock_put(zebra.inputs.soft_in_2)

    mock_beam_x.assert_called_once_with(
        pytest.approx(1597.06, 1e-2), wait=True
    )  # Check beam center set
    assert dummy_params_without_pp.total_num_images == 400
    mock_get_chip_prog.assert_called_once_with(dummy_params_without_pp)
    mock_motion_program.asset_called_once()
    mock_start.assert_called_once()
    mock_pmac_str.assert_called_once_with(
        "!x0y0z0", wait=True
    )  # Check pmac moved to start
    assert fake_dcid.notify_start.call_count == 1
    mock_zebra_input.assert_called_once_with(
        "Yes", wait=True
    )  # Check fast shutter open
    fake_nexgen.assert_called_once_with(
        mock_get_chip_prog.return_value,
        dummy_params_without_pp,
        0.6,
        (ANY, ANY),
        None,
    )
    mock_kickoff.assert_called_once_with(
        pmac, dummy_params_without_pp
    )  # Check collection kick off


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.sup.get_beam_center_device"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.Path.mkdir"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.read_parameters"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bps.sleep"
)
def test_setup_tasks_in_run_fixed_target_plan(
    fake_sleep,
    fake_read,
    fake_mkdir,
    mock_beam_center,
    zebra,
    pmac,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    shutter,
    dcm,
    mirrors,
    RE,
    dummy_params_without_pp,
):
    mock_attenuator = MagicMock()
    fake_read.side_effect = [fake_generator(dummy_params_without_pp)]
    with (
        patch(
            "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.bpp.contingency_wrapper"
        ),
        patch(
            "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Collect_py3v1.upload_chip_map_to_geobrick"
        ) as patch_upload,
    ):
        RE(
            run_fixed_target_plan(
                zebra,
                pmac,
                aperture,
                backlight,
                beamstop,
                detector_stage,
                shutter,
                dcm,
                mirrors,
                mock_attenuator,
            )
        )
        fake_mkdir.assert_called_once()
        mock_beam_center.assert_called_once()
        patch_upload.assert_called_once_with(pmac, dummy_params_without_pp.chip_map)
