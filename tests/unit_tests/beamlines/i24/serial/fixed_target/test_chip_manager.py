import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, mock_open, patch

import pytest
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.i24.pmac import PMAC
from ophyd_async.testing import get_mock_put

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import Fiducials
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1 import (
    cs_maker,
    cs_reset,
    fiducial,
    initialise_stages,
    laser_control,
    moveto,
    moveto_preset,
    pumpprobe_calc,
    read_parameters,
    scrape_mtr_directions,
    scrape_mtr_fiducials,
    set_pmac_strings_for_cs,
    upload_chip_map_to_geobrick,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger

from ..conftest import fake_generator

chipmap_str = """01status    P3011       1
02status    P3021       0
03status    P3031       0
04status    P3041       0"""

mtr_dir_str = """#Some words
mtr1_dir=1
mtr2_dir=-1
mtr3_dir=-1"""

fiducial_1_str = """MTR RBV Corr
MTR1 0 1
MTR2 1 -1
MTR3 0 -1"""

cs_json = '{"scalex":1, "scaley":2, "scalez":3, "skew":-0.5, "Sx_dir":1, "Sy_dir":-1, "Sz_dir":0}'


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.get_detector_type"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.get_chip_format"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1._read_visit_directory_from_file"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.SSX_LOGGER"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.bps.rd")
def test_read_parameters(
    fake_rd,
    fake_log,
    mock_read_visit,
    fake_caget,
    fake_chip,
    fake_det,
    detector_stage,
    RE,
):
    mock_attenuator = MagicMock()
    fake_det.side_effect = [fake_generator(Eiger())]
    fake_rd.side_effect = [fake_generator(0.3)]
    with patch(
        "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.FixedTargetParameters",
    ):
        RE(read_parameters(detector_stage, mock_attenuator))

    assert fake_caget.call_count == 12
    assert fake_log.info.call_count == 3


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.sys")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.get_detector_type"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caput")
async def test_initialise(
    fake_caput: MagicMock,
    fake_det: MagicMock,
    fake_sys: MagicMock,
    pmac: PMAC,
    RE,
):
    RE(initialise_stages(pmac))

    assert await pmac.x.velocity.get_value() == 20
    assert await pmac.y.acceleration_time.get_value() == 0.01
    assert await pmac.z.high_limit_travel.get_value() == 5.1
    assert await pmac.z.low_limit_travel.get_value() == -4.1

    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_pmac_str.assert_has_calls(
        [
            call("m508=100 m509=150", wait=True),
            call("m608=100 m609=150", wait=True),
            call("m708=100 m709=150", wait=True),
            call("m808=100 m809=150", wait=True),
        ]
    )


@pytest.mark.parametrize(
    "fake_chip_map",
    [[10], [1, 2, 15, 16], list(range(33, 65))],  # 1 block, 1 corner, half chip
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.bps.sleep"
)
def test_upload_chip_map_to_geobrick(
    fake_sleep: MagicMock, fake_chip_map: list[int], pmac: PMAC, RE
):
    tot_blocks = 64
    RE(upload_chip_map_to_geobrick(pmac, fake_chip_map))

    mock_pmac_str = get_mock_put(pmac.pmac_string)
    assert mock_pmac_str.call_count == tot_blocks

    pvar_zero_calls = [
        call(f"P3{i:02d}1=0", wait=True) for i in range(1, 65) if i not in fake_chip_map
    ]

    pvar_one_calls = [call(f"P3{i:02d}1=1", wait=True) for i in fake_chip_map]

    assert len(pvar_zero_calls) == tot_blocks - len(fake_chip_map)
    assert len(pvar_one_calls) == len(fake_chip_map)

    mock_pmac_str.assert_has_calls(pvar_one_calls, any_order=True)
    mock_pmac_str.assert_has_calls(pvar_zero_calls, any_order=True)


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
async def test_moveto_oxford_origin(fake_caget: MagicMock, pmac: PMAC, RE):
    fake_caget.return_value = 0
    RE(moveto(Fiducials.origin, pmac))
    assert fake_caget.call_count == 1
    assert await pmac.x.user_setpoint.get_value() == 0.0
    assert await pmac.y.user_setpoint.get_value() == 0.0


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
async def test_moveto_oxford_inner_f1(fake_caget: MagicMock, pmac: PMAC, RE):
    fake_caget.return_value = 1
    RE(moveto(Fiducials.fid1, pmac))
    assert fake_caget.call_count == 1
    assert await pmac.x.user_setpoint.get_value() == 24.60
    assert await pmac.y.user_setpoint.get_value() == 0.0


async def test_moveto_chip_aspecific(pmac: PMAC, RE):
    RE(moveto("zero", pmac))
    assert await pmac.pmac_string.get_value() == "!x0y0z0"


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caput")
async def test_moveto_preset(
    fake_caput: MagicMock,
    pmac: PMAC,
    beamstop: Beamstop,
    backlight: DualBacklight,
    detector_stage: DetectorMotion,
    RE,
):
    RE(moveto_preset("zero", pmac, beamstop, backlight, detector_stage))
    assert await pmac.pmac_string.get_value() == "!x0y0z0"

    RE(moveto_preset("load_position", pmac, beamstop, backlight, detector_stage))
    assert await beamstop.pos_select.get_value() == "Robot"
    assert await backlight.backlight_position.pos_level.get_value() == "Out"
    assert await detector_stage.z.user_setpoint.get_value() == 1300


@pytest.mark.parametrize(
    "pos_request, expected_num_caput, expected_pmac_move, other_devices",
    [
        ("collect_position", 1, [0.0, 0.0, 0.0], True),
        ("microdrop_position", 0, [6.0, -7.8, 0.0], False),
    ],
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caput")
async def test_moveto_preset_with_pmac_move(
    fake_caput: MagicMock,
    pos_request: str,
    expected_num_caput: int,
    expected_pmac_move: list,
    other_devices: bool,
    pmac: PMAC,
    beamstop: Beamstop,
    backlight: DualBacklight,
    detector_stage: DetectorMotion,
    RE,
):
    RE(moveto_preset(pos_request, pmac, beamstop, backlight, detector_stage))
    assert fake_caput.call_count == expected_num_caput

    assert await pmac.x.user_setpoint.get_value() == expected_pmac_move[0]
    assert await pmac.y.user_setpoint.get_value() == expected_pmac_move[1]
    assert await pmac.z.user_setpoint.get_value() == expected_pmac_move[2]

    if other_devices:
        assert await beamstop.pos_select.get_value() == "Data Collection"
        assert await backlight.backlight_position.pos_level.get_value() == "In"


@pytest.mark.parametrize(
    "laser_setting, expected_pmac_string",
    [
        ("laser1on", " M712=1 M711=1"),
        ("laser1off", " M712=0 M711=1"),
        ("laser2on", " M812=1 M811=1"),
        ("laser2off", " M812=0 M811=1"),
    ],
)
async def test_laser_control_on_and_off(
    laser_setting: str, expected_pmac_string: str, pmac: PMAC, RE
):
    RE(laser_control(laser_setting, pmac))

    assert await pmac.pmac_string.get_value() == expected_pmac_string


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.bps.sleep"
)
def test_laser_control_burn_setting(
    fake_sleep: MagicMock, fake_caget: MagicMock, pmac: PMAC, RE
):
    fake_caget.return_value = 0.1
    RE(laser_control("laser1burn", pmac))

    fake_sleep.assert_called_once_with(0.1)
    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_pmac_str.assert_has_calls(
        [
            call(" M712=1 M711=1", wait=True),
            call(" M712=0 M711=1", wait=True),
        ]
    )


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
    mock_open(read_data=mtr_dir_str),
)
def test_scrape_mtr_directions():
    res = scrape_mtr_directions()
    assert len(res) == 3
    assert res == (1.0, -1.0, -1.0)


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_directions"
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.bps.rd")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.PARAM_FILE_PATH_FT"
)
def test_fiducial_writes_correct_values_to_file(
    fake_param_path, patch_read, patch_mtr, pmac, RE
):
    fake_param_path.return_value = Path("/tmp/params")
    mtr_values = (1.0, -1.0, -1.0)
    patch_mtr.return_value = mtr_values

    pos = (1.02, 4.5, 0.0)

    patch_read.side_effect = [
        fake_generator(pos[0]),
        fake_generator(pos[1]),
        fake_generator(pos[2]),
    ]

    expected_write_calls = [
        call(fake_param_path / "fiducial_1.txt", "w"),
        call().write("MTR\tRBV\tCorr\n"),
        call().write(f"MTR1\t{pos[0]:1.4f}\t{mtr_values[0]:f}\n"),
        call().write(f"MTR2\t{pos[1]:1.4f}\t{mtr_values[1]:f}\n"),
        call().write(f"MTR3\t{pos[2]:1.4f}\t{mtr_values[2]:f}"),
    ]
    with patch(
        "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
        mock_open(),
    ) as mock_file:
        RE(fiducial(1, pmac))

        mock_file.assert_has_calls(expected_write_calls, any_order=True)
        fake_param_path.mkdir.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
    mock_open(read_data=fiducial_1_str),
)
def test_scrape_mtr_fiducials():
    res = scrape_mtr_fiducials(1)
    assert len(res) == 3
    assert res == (0.0, 1.0, 0.0)


def test_cs_pmac_str_set(pmac: PMAC, RE):
    RE(
        set_pmac_strings_for_cs(
            pmac,
            {
                "cs1": "#1->-10000X+0Y+0Z",
                "cs2": "#2->+0X+10000Y+0Z",
                "cs3": "#3->0X+0Y+10000Z",
            },
        )
    )
    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_pmac_str.assert_has_calls(
        [
            call("&2", wait=True),
            call("#1->-10000X+0Y+0Z", wait=True),
            call("#2->+0X+10000Y+0Z", wait=True),
            call("#3->0X+0Y+10000Z", wait=True),
        ]
    )


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.set_pmac_strings_for_cs"
)
def test_cs_reset(mock_set_pmac_str: MagicMock, pmac: PMAC, RE):
    RE(cs_reset(pmac))
    mock_set_pmac_str.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
    mock_open(read_data='{"a":11, "b":12,}'),
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_directions"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_fiducials"
)
def test_cs_maker_raises_error_for_invalid_json(
    fake_fid: MagicMock,
    fake_dir: MagicMock,
    fake_caget: MagicMock,
    pmac: PMAC,
    RE,
):
    fake_dir.return_value = (1, 1, 1)
    fake_fid.return_value = (0, 0, 0)
    with pytest.raises(json.JSONDecodeError):
        RE(cs_maker(pmac))


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
    mock_open(read_data='{"scalex":11, "skew":12}'),
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_directions"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_fiducials"
)
def test_cs_maker_raises_error_for_missing_key_in_json(
    fake_fid: MagicMock,
    fake_dir: MagicMock,
    fake_caget: MagicMock,
    pmac: PMAC,
    RE,
):
    fake_dir.return_value = (1, 1, 1)
    fake_fid.return_value = (0, 0, 0)
    with pytest.raises(KeyError):
        RE(cs_maker(pmac))


@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.open",
    mock_open(read_data=cs_json),
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_directions"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.scrape_mtr_fiducials"
)
def test_cs_maker_raises_error_for_wrong_direction_in_json(
    fake_fid: MagicMock,
    fake_dir: MagicMock,
    fake_caget: MagicMock,
    pmac: PMAC,
    RE,
):
    fake_dir.return_value = (1, 1, 1)
    fake_fid.return_value = (0, 0, 0)
    with pytest.raises(ValueError):
        RE(cs_maker(pmac))


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caput")
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1.caget")
def test_pumpprobe_calc(fake_caget: MagicMock, fake_caput: MagicMock, RE):
    fake_caget.side_effect = [0.01, 0.005]
    RE(pumpprobe_calc())
    assert fake_caget.call_count == 2
    assert fake_caput.call_count == 5
    fake_caput.assert_has_calls(
        [
            call(ANY, 0.62),
            call(ANY, 1.24),
            call(ANY, 1.86),
            call(ANY, 3.1),
            call(ANY, 6.2),
        ]
    )
