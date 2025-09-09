from enum import StrEnum


class Subjects(StrEnum):
    UDC_STARTED = "UDC Started"
    UDC_BATON_RELEASED = "UDC Baton was released"
    UDC_COMPLETED = "UDC Completed"
    UDC_RESUMED_OPERATION = "UDC Resumed operation"
    UDC_SUSPENDED_OPERATION = "UDC Suspended operation"
    NEW_CONTAINER = "Hyperion is collecting from a new container"
    NEW_VISIT = "Hyperion has changed visit"
    SAMPLE_ERROR = "Hyperion has encountered a sample error"
    BEAMLINE_ERROR = "Hyperion has encountered a beamline error"
