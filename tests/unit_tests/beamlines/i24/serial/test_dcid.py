from unittest.mock import patch

import pytest
from dodal.devices.beamlines.i24.beam_center import DetectorBeamCenter
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.focus_mirrors import FocusMirrorsMode
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.dcid import (
    DCID,
    generate_ssx_event_chain,
    get_resolution,
    read_beam_info_from_hardware,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import PumpProbeSetting
from mx_bluesky.beamlines.i24.serial.parameters import (
    BeamSettings,
    DetectorName,
    ExtruderParameters,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger


def test_read_beam_info_from_hardware(
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    eiger_beam_center: DetectorBeamCenter,
    run_engine,
):
    set_mock_value(dcm.wavelength_in_a.user_readback, 0.6)
    expected_beam_x = 1605 * 0.075
    expected_beam_y = 1702 * 0.075

    res = run_engine(
        read_beam_info_from_hardware(
            dcm, mirrors, eiger_beam_center, DetectorName.EIGER
        )
    ).plan_result  # type: ignore

    assert res.wavelength_in_a == 0.6
    assert res.beam_size_in_um == (7, 7)
    assert res.beam_center_in_mm == (expected_beam_x, expected_beam_y)


def test_get_resolution():
    distance = 100
    wavelength = 0.649

    eiger_resolution = get_resolution(Eiger(), distance, wavelength)

    assert eiger_resolution == 0.78


@patch("mx_bluesky.beamlines.i24.serial.dcid.get_resolution")
@patch("mx_bluesky.beamlines.i24.serial.dcid.SSX_LOGGER")
@patch("mx_bluesky.beamlines.i24.serial.dcid.json")
def test_generate_dcid_for_eiger(
    fake_json, fake_log, patch_resolution, dummy_params_ex, run_engine
):
    test_dcid = DCID(
        server="fake_server",
        emit_errors=False,
        expt_params=dummy_params_ex,
    )

    assert isinstance(test_dcid.detector, Eiger)
    assert isinstance(test_dcid.parameters, ExtruderParameters)

    beam_settings = BeamSettings(
        wavelength_in_a=0.6, beam_size_in_um=(7, 7), beam_center_in_mm=(100, 100)
    )

    with (
        patch("mx_bluesky.beamlines.i24.serial.dcid.requests") as patch_request,
        patch("mx_bluesky.beamlines.i24.serial.dcid.get_auth_header") as fake_auth,
    ):
        test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)
        patch_resolution.assert_called_once_with(
            test_dcid.detector,
            dummy_params_ex.detector_distance_mm,
            beam_settings.wavelength_in_a,
        )
        fake_auth.assert_called_once()
        fake_json.dumps.assert_called_once()
        patch_request.post.assert_called_once()

        expt_type = patch_request.post.call_args.kwargs["json"]["group"][
            "experimentType"
        ]
        assert (
            not isinstance(expt_type, SSXType)  # needs to be serialisable
            and expt_type == dummy_params_ex.ispyb_experiment_type.value
        )
        assert patch_request.post.call_args.kwargs["json"]["detectorId"] == 94
        assert "beamSizeAtSampleX" in list(
            patch_request.post.call_args.kwargs["json"].keys()
        )
        assert (
            len(
                patch_request.post.call_args.kwargs["json"]["ssx"]["eventChain"][
                    "events"
                ]
            )
            == 1
        )  # no pump probe


def _events(parameters, shots_per_position: int = 1, pump_probe: bool = False) -> list:
    chain = generate_ssx_event_chain(parameters, shots_per_position, pump_probe)
    assert chain is not None
    return chain["eventChain"]["events"]


@pytest.mark.parametrize(
    "shots_per_position, expected_name", [(1, "probe"), (5, "dose")]
)
def test_ssx_event_chain_without_pump_probe_is_a_single_xray_group(
    dummy_params_ex, shots_per_position, expected_name
):
    assert _events(dummy_params_ex, shots_per_position) == [
        {
            "name": expected_name,
            "offset": 0,
            "duration": dummy_params_ex.exposure_time_s,
            "period": dummy_params_ex.exposure_time_s,
            "repetition": shots_per_position,
            "eventType": "XrayDetection",
        }
    ]


def test_ssx_event_chain_extruder_pump_follows_the_first_image(dummy_params_ex):
    params = dummy_params_ex.model_copy(
        update={"pump_status": True, "laser_delay_s": 0.02, "laser_dwell_s": 0.005}
    )

    events = _events(params, pump_probe=True)

    assert len(events) == 2
    assert events[1] == {
        "name": "Laser probe",
        "offset": 0.02,
        "duration": 0.005,
        "repetition": 1,
        "eventType": "LaserExcitation",
    }


@pytest.mark.parametrize(
    "pump_repeat, expected_offset",
    [
        (PumpProbeSetting.Short1, -0.02),
        (PumpProbeSetting.Short2, 0.02),
        (PumpProbeSetting.Repeat1, -0.02),
    ],
)
def test_ssx_event_chain_fixed_target_pump_precedes_the_first_image(
    dummy_params_without_pp, pump_repeat, expected_offset
):
    # Short2 probes then pumps, everything else pumps before the first image
    params = dummy_params_without_pp.model_copy(
        update={
            "pump_repeat": pump_repeat,
            "laser_delay_s": 0.02,
            "laser_dwell_s": 0.005,
        }
    )

    events = _events(params, pump_probe=True)

    assert events[1]["offset"] == expected_offset


def test_ssx_event_chain_checker_pattern_adds_an_apo_group(dummy_params_without_pp):
    params = dummy_params_without_pp.model_copy(
        update={
            "checker_pattern": True,
            "pump_repeat": PumpProbeSetting.Short1,
            "laser_dwell_s": 0.005,
        }
    )

    xray_events = [
        event
        for event in _events(params, 3, pump_probe=True)
        if event["eventType"] == "XrayDetection"
    ]

    assert [event["name"] for event in xray_events] == ["dose", "apo"]
    # The unpumped group only starts once the pumped group has finished
    assert xray_events[1]["offset"] == pytest.approx(
        xray_events[0]["offset"] + 3 * params.exposure_time_s
    )
    assert xray_events[1]["repetition"] == xray_events[0]["repetition"] == 3


def test_ssx_event_chain_has_no_apo_group_without_checker_pattern(
    dummy_params_without_pp,
):
    assert [event["name"] for event in _events(dummy_params_without_pp, 3)] == ["dose"]


def test_ssx_event_chain_has_no_apo_group_without_pump_probe(dummy_params_without_pp):
    # The motion program only honours the checker pattern when pumping
    params = dummy_params_without_pp.model_copy(update={"checker_pattern": True})

    assert [event["name"] for event in _events(params, 3)] == ["dose"]


def test_ssx_event_chain_extruder_never_gets_an_apo_group(dummy_params_ex):
    # ExtruderParameters has no checker_pattern field at all
    assert [event["name"] for event in _events(dummy_params_ex, 3)] == ["dose"]
