from unittest.mock import MagicMock

import pytest
from bluesky import plan_stubs as bps, RunEngine
from dodal.beamlines import i03
from dodal.devices.aperture import Aperture
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.beamlines.i19.diffractometer import DetectorMotion
from dodal.devices.detector import DetectorParams
from dodal.devices.eiger import EigerDetector
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from mx_bluesky.common.device_setup_plans.detector.beamline_specific import BeamlineSpecificDetectorFeatures
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.device_composites import DiffractionExtendedDevices
from mx_bluesky.common.parameters.gridscan import create_detector_params_for_grid_scan
from ophyd_async.core import get_mock_put

from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from unit_tests.t01 import synchrotron


@pytest.fixture()
def mock_eiger():
    eiger = i03.eiger.build(mock=True)
    eiger.detector_params = MagicMock()
    eiger.async_stage = MagicMock()
    eiger.disarm_detector = MagicMock()
    return eiger


@pytest.fixture()
def diffraction_extended_devices(aperture_scatterguard: ApertureScatterguard,
                                 beamstop_phase1: Beamstop,
                                 detector_motion: DetectorMotion,
                                 mock_eiger: EigerDetector,
                                 synchrotron: Synchrotron,
                                 smargon: Smargon) -> DiffractionExtendedDevices:
    return DiffractionExtendedDevices(
        aperture_scatterguard=aperture_scatterguard,
        beamstop=beamstop_phase1,
        detector_motion=detector_motion,
        detector=mock_eiger,
        synchrotron=synchrotron,
        gonio=smargon
    )


@pytest.fixture
def detector_params(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
) -> DetectorParams:
    return create_detector_params_for_grid_scan(minimal_diffraction_expt_with_sample)


class MyTestError(Exception):
    pass


def test_given_plan_raises_when_exception_raised_then_eiger_disarmed_and_correct_exception_returned(
    beamline_specific_detector: BeamlineSpecificDetectorFeatures,
    detector_params: DetectorParams,
    diffraction_extended_devices: DiffractionExtendedDevices,

    beamstop_phase1, mock_eiger, detector_motion, run_engine
):
    def my_plan():
        yield from bps.null()
        raise MyTestError()

    with pytest.raises(MyTestError):
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamline_specific_detector,
                detector_params,
                diffraction_extended_devices,
                100,
                my_plan()
            )
        )

    # Check detector was armed
    diffraction_extended_devices.detector.async_stage.assert_called_once()
    diffraction_extended_devices.detector.disarm_detector.assert_called_once()


@pytest.fixture()
def null_plan():
    yield from bps.null()


def test_given_shutter_open_fails_then_eiger_disarmed_and_correct_exception_returned(
    beamline_specific_detector: BeamlineSpecificDetectorFeatures,
    detector_params: DetectorParams,
    diffraction_extended_devices: DiffractionExtendedDevices,
    null_plan,
    run_engine: RunEngine
):
    diffraction_extended_devices.detector_motion = MagicMock()
    diffraction_extended_devices.detector_motion.z.set = MagicMock(side_effect=MyTestError())

    with pytest.raises(MyTestError):
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamline_specific_detector,
                detector_params,
                diffraction_extended_devices,
                100,
                null_plan
            )
        )

    diffraction_extended_devices.detector.async_stage.assert_called_once()
    diffraction_extended_devices.detector_motion.z.set.assert_called_once()
    diffraction_extended_devices.detector.disarm_detector.assert_called_once()


def test_given_detector_move_fails_then_eiger_disarmed_and_correct_exception_returned(
        beamline_specific_detector: BeamlineSpecificDetectorFeatures,
        detector_params: DetectorParams,
        diffraction_extended_devices: DiffractionExtendedDevices,
        null_plan,
        run_engine: RunEngine
):
    diffraction_extended_devices.detector_motion.shutter.set = MagicMock(side_effect=MyTestError)

    with pytest.raises(MyTestError):
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamline_specific_detector,
                detector_params,
                diffraction_extended_devices,
                100,
                null_plan
            )
        )
    diffraction_extended_devices.detector.async_stage.assert_called_once()

    def wait_for_set():
        yield from bps.wait(group="ready_for_data_collection")

    run_engine(wait_for_set())
    get_mock_put(diffraction_extended_devices.detector_motion.z.user_setpoint).assert_called_once()
    diffraction_extended_devices.detector.disarm_detector.assert_called_once()
