import re

import pytest

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_utils import (
    get_current_time_string,
)

TIME_FORMAT_REGEX = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


def test_get_current_time_string():
    current_time = get_current_time_string()

    assert isinstance(current_time, str)
    assert re.match(TIME_FORMAT_REGEX, current_time) is not None


@pytest.mark.parametrize(
    "visit_string, expected_proposal, expected_session",
    [
        ("cm6477-45", "cm6477", 45),
        ("mx54663-1", "mx54663", 1),
        ("ea54663985-13651", "ea54663985", 13651),
    ],
)
def test_proposal_and_session_from_visit_string_happy_path(
    visit_string: str, expected_proposal: str, expected_session: int
):
    proposal, session = get_proposal_and_session_from_visit_string(visit_string)
    assert proposal == expected_proposal
    assert session == expected_session


@pytest.mark.parametrize(
    "visit_string, exception_type",
    [
        ("cm647-7-45", AssertionError),
        ("mx54663.1", AssertionError),
        ("mx54663-pop", ValueError),
    ],
)
def test_given_invalid_visit_string_get_proposal_and_session_throws(
    visit_string: str, exception_type
):
    with pytest.raises(exception_type):
        get_proposal_and_session_from_visit_string(visit_string)
