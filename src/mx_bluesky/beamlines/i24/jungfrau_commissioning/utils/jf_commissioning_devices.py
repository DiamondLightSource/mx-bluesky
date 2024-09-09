from enum import IntEnum

from ophyd import Component as Cpt
from ophyd import Device, EpicsSignal, EpicsSignalRO


class TriggerMode(IntEnum):
    SOFTWARE = 0
    HARDWARE = 1


class JungfrauM1(Device):
    trigger_mode = Cpt(EpicsSignal, "Timing")
    trigger_count = Cpt(EpicsSignal, "TriggerCount")
    acquire_period_s = Cpt(EpicsSignal, "AcquirePeriod")
    exposure_time_s = Cpt(EpicsSignal, "ExposureTime")
    acquire_rbv = Cpt(EpicsSignal, "Acquire_RBV")
    state_rbv = Cpt(EpicsSignal, "State_RBV")
    writing_rbv = Cpt(EpicsSignal, "Writing_RBV")
    acquire_start = Cpt(EpicsSignal, "Acquire")
    clear_error = Cpt(EpicsSignal, "ClearError")
    frames_written_rbv = Cpt(EpicsSignal, "FramesWritten_RBV")
    frame_count = Cpt(EpicsSignal, "FrameCount")
    gain_mode = Cpt(EpicsSignal, "GainMode", string=True)
    error_rbv = Cpt(EpicsSignal, "Error_RBV", string=True)
    file_directory = Cpt(EpicsSignal, "FileDirectory", string=True)
    file_name = Cpt(EpicsSignal, "FileName", string=True)


class ReadOnlyEnergyAndAttenuator(Device):
    transmission = Cpt(EpicsSignalRO, "-OP-ATTN-01:MATCH")
    wavelength = Cpt(EpicsSignalRO, "-MO-DCM-01:LAMBDA")
    energy = Cpt(EpicsSignalRO, "-MO-DCM-01:ENERGY.RBV")
    intensity = Cpt(EpicsSignalRO, "-EA-XBPM-01:SumAll:MeanValue_RBV")
    flux_xbpm2 = Cpt(EpicsSignalRO, "-EA-FLUX-01:XBPM-02")
    flux_xbpm3 = Cpt(EpicsSignalRO, "-EA-FLUX-01:XBPM-03")
    shutter = Cpt(EpicsSignalRO, "-PS-SHTR-01:CON")
    slow_shutter = Cpt(EpicsSignalRO, "-EA-SHTR-02:M32")


class SetAttenuator(Device):
    transmission_setpoint = Cpt(EpicsSignal, "-OP-ATTN-01:T2A:SETVAL1")
    filter_1_moving = Cpt(EpicsSignal, "-OP-ATTN-01:MP1:INPOS")
    filter_2_moving = Cpt(EpicsSignal, "-OP-ATTN-01:MP2:INPOS")
