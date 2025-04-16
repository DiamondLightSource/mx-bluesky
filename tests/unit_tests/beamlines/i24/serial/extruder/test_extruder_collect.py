from unittest.mock import ANY, MagicMock, call, patch

import pytest
from dodal.beamlines.i24 import I24_ZEBRA_MAPPING
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2 import (
    collection_aborted_plan,
    collection_complete_plan,
    enter_hutch,
    initialise_extruder,
    laser_check,
    main_extruder_plan,
    read_parameters,
    tidy_up_at_collection_end_plan,
)
from mx_bluesky.beamlines.i24.serial.parameters import BeamSettings, ExtruderParameters
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, Pilatus

from ..conftest import TEST_LUT, fake_generator


@pytest.fixture
def dummy_params():
    params = {
        "visit": "/tmp/dls/i24/extruder/foo",
        "directory": "bar",
        "filename": "protein",
        "exposure_time_s": 0.1,
        "detector_distance_mm": 100,
        "detector_name": "eiger",
        "transmission": 1.0,
        "num_images": 10,
        "pump_status": False,
    }
    return ExtruderParameters(**params)


@pytest.fixture
def dummy_params_pp():
    params_pp = {
        "visit": "/tmp/dls/i24/extruder/foo",
        "directory": "bar",
        "filename": "protein",
        "exposure_time_s": 0.1,
        "detector_distance_mm": 100,
        "detector_name": "pilatus",
        "transmission": 1.0,
        "num_images": 10,
        "pump_status": True,
        "laser_dwell_s": 0.01,
        "laser_delay_s": 0.005,
    }
    return ExtruderParameters(**params_pp)


@pytest.fixture
def dummy_beam_settings():
    return BeamSettings(
        wavelength_in_a=0.6, beam_size_in_um=(7, 7), beam_center_in_mm=(120.4, 127.6)
    )


@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.get_detector_type"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caget")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2._read_visit_directory_from_file"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.SSX_LOGGER"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.rd")
def test_read_parameters(
    fake_rd,
    fake_log,
    mock_read_visit,
    fake_caget,
    fake_det,
    detector_stage,
    RE,
):
    mock_attenuator = MagicMock()
    fake_det.side_effect = [fake_generator(Eiger())]
    fake_rd.side_effect = [fake_generator(0.3)]
    with patch(
        "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.ExtruderParameters",
    ):
        RE(read_parameters(detector_stage, mock_attenuator))

    assert fake_caget.call_count == 8
    fake_log.warning.assert_called_once()
    assert fake_log.info.call_count == 3


@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caget")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.get_detector_type"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.SSX_LOGGER"
)
def test_initialise_extruder(
    fake_log,
    fake_det,
    fake_caput,
    fake_caget,
    detector_stage,
    RE,
):
    fake_caget.return_value = "/path/to/visit"
    fake_det.side_effect = [fake_generator(Eiger())]
    RE(initialise_extruder(detector_stage))
    assert fake_caput.call_count == 10
    assert fake_caget.call_count == 1


async def test_enterhutch(detector_stage, RE):
    RE(enter_hutch(detector_stage))
    assert await detector_stage.z.user_setpoint.get_value() == 1480


@pytest.mark.parametrize(
    "laser_mode, det_type, expected_in1, expected_out",
    [
        ("laseron", Eiger(), "Yes", I24_ZEBRA_MAPPING.sources.SOFT_IN3),
        ("laseroff", Eiger(), "No", I24_ZEBRA_MAPPING.sources.DISCONNECT),
        ("laseron", Pilatus(), "Yes", I24_ZEBRA_MAPPING.sources.SOFT_IN3),
        ("laseroff", Pilatus(), "No", I24_ZEBRA_MAPPING.sources.DISCONNECT),
    ],
)
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.get_detector_type"
)
async def test_laser_check(
    fake_det,
    laser_mode,
    expected_in1,
    expected_out,
    det_type,
    zebra,
    detector_stage,
    RE,
):
    fake_det.side_effect = [fake_generator(det_type)]
    RE(laser_check(laser_mode, zebra, detector_stage))

    TTL = (
        I24_ZEBRA_MAPPING.outputs.TTL_EIGER
        if isinstance(det_type, Pilatus)
        else I24_ZEBRA_MAPPING.outputs.TTL_PILATUS
    )
    assert await zebra.inputs.soft_in_1.get_value() == expected_in1
    assert await zebra.output.out_pvs[TTL].get_value() == expected_out


@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.sleep"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.call_nexgen"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caget")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.sup")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.setup_zebra_for_quickshot_plan"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.rd")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.read_beam_info_from_hardware"
)
def test_run_extruder_quickshot_with_eiger(
    mock_read_beam_info,
    fake_read,
    mock_quickshot_plan,
    fake_sup,
    fake_caget,
    fake_caput,
    fake_nexgen,
    fake_dcid,
    fake_sleep,
    RE,
    zebra,
    shutter,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    dcm,
    mirrors,
    eiger_beam_center,
    dummy_params,
    dummy_beam_settings,
):
    fake_start_time = MagicMock()
    mock_read_beam_info.side_effect = [fake_generator(dummy_beam_settings)]
    # Mock end of data collection (zebra disarmed)
    fake_read.side_effect = [
        fake_generator(1605),  # beam center
        fake_generator(1702),
        fake_generator(0),  # zebra disarm
    ]
    with patch(
        "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.BEAM_CENTER_LUT_FILES",
        new=TEST_LUT,
    ):
        RE(
            main_extruder_plan(
                zebra,
                aperture,
                backlight,
                beamstop,
                detector_stage,
                shutter,
                dcm,
                mirrors,
                eiger_beam_center,
                dummy_params,
                fake_dcid,
                fake_start_time,
            )
        )
    fake_nexgen.assert_called_once_with(
        None, dummy_params, 0.6, (1605, 1702), fake_start_time
    )
    assert fake_dcid.generate_dcid.call_count == 1
    assert fake_dcid.notify_start.call_count == 1
    assert fake_sup.setup_beamline_for_collection_plan.call_count == 1
    mock_quickshot_plan.assert_called_once()
    mock_read_beam_info.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.sleep"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.DCID")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caget")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.sup")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.setup_zebra_for_extruder_with_pump_probe_plan"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.rd")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.read_beam_info_from_hardware"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.get_pilatus_filename_template_from_device"
)
def test_run_extruder_pump_probe_with_pilatus(
    mock_pilatus_temp,
    mock_read_beam_info,
    fake_read,
    mock_pp_plan,
    fake_sup,
    fake_caget,
    fake_caput,
    fake_dcid,
    fake_sleep,
    RE,
    zebra,
    shutter,
    aperture,
    backlight,
    beamstop,
    detector_stage,
    dcm,
    mirrors,
    pilatus_beam_center,
    dummy_params_pp,
):
    fake_start_time = MagicMock()
    set_mock_value(dcm.wavelength_in_a.user_readback, 0.6)
    # Mock end of data collection (zebra disarmed)
    fake_read.side_effect = [fake_generator(0)]
    mock_pilatus_temp.side_effect = [fake_generator("test_00001_#####.cbf")]
    with patch(
        "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.BEAM_CENTER_LUT_FILES",
        new=TEST_LUT,
    ):
        RE(
            main_extruder_plan(
                zebra,
                aperture,
                backlight,
                beamstop,
                detector_stage,
                shutter,
                dcm,
                mirrors,
                pilatus_beam_center,
                dummy_params_pp,
                fake_dcid,
                fake_start_time,
            )
        )
    mock_pilatus_temp.assert_called_once()
    assert fake_dcid.generate_dcid.call_count == 1
    assert fake_dcid.notify_start.call_count == 1
    assert fake_sup.move_detector_stage_to_position_plan.call_count == 1
    mock_pp_plan.assert_called_once()

    shutter_call_list = [
        call("Reset", wait=True),
        call("Open", wait=True),
    ]
    mock_shutter = get_mock_put(shutter.control)
    mock_shutter.assert_has_calls(shutter_call_list)
    mock_read_beam_info.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.reset_zebra_when_collection_done_plan"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.DCID")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caget")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.sup")
def test_tidy_up_at_collection_end_plan_with_eiger(
    fake_sup,
    fake_caget,
    fake_caput,
    fake_dcid,
    mock_reset_zebra_plan,
    RE,
    zebra,
    shutter,
    dummy_params,
    dcm,
):
    RE(tidy_up_at_collection_end_plan(zebra, shutter, dummy_params, fake_dcid, dcm))

    mock_reset_zebra_plan.assert_called_once()
    mock_shutter = get_mock_put(shutter.control)
    mock_shutter.assert_has_calls([call("Close", wait=True)])

    assert fake_dcid.notify_end.call_count == 1
    assert fake_caget.call_count == 1

    fake_sup.eiger.assert_called_once_with("return-to-normal", None, dcm)


@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.sleep"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.disarm_zebra"
)
def test_aborted_plan_with_pilatus(
    mock_disarm, fake_dcid, fake_caput, fake_sleep, RE, zebra
):
    RE(collection_aborted_plan(zebra, "pilatus", fake_dcid))

    mock_disarm.assert_called_once()
    fake_caput.assert_has_calls([call(ANY, 0)])
    fake_dcid.collection_complete.assert_called_once_with(ANY, aborted=True)


@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.DCID")
@patch(
    "mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.bps.sleep"
)
@patch("mx_bluesky.beamlines.i24.serial.extruder.i24ssx_Extruder_Collect_py3v2.caput")
def test_collection_complete_plan_with_eiger(
    fake_caput, fake_sleep, fake_dcid, dummy_params, RE
):
    RE(
        collection_complete_plan(
            dummy_params.collection_directory, dummy_params.detector_name, fake_dcid
        )
    )

    call_list = [call(ANY, 0), call(ANY, "Done")]
    fake_caput.assert_has_calls(call_list)

    fake_dcid.collection_complete.assert_called_once_with(ANY, aborted=False)
