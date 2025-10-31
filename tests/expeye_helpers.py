import dataclasses
import json
import re
from functools import partial

import pytest
import responses
from requests import PreparedRequest

TEST_DATA_COLLECTION_IDS = (12, 13)
TEST_DATA_COLLECTION_GROUP_ID = 34
TEST_GRID_INFO_IDS = (56, 57)

URL_PREFIX = "(http://[^/]+|)"
DCGS_RE = re.compile(URL_PREFIX + r"/proposals/([a-z]+\d+)/sessions/(\d+)/data-groups$")
DCG_RE = re.compile(URL_PREFIX + r"/data-groups/(\d+)$")
DCS_RE = re.compile(URL_PREFIX + r"/data-groups/(\d+)/data-collections$")
DC_RE = re.compile(URL_PREFIX + r"/data-collections/(\d+)$")
DC_COMMENT_RE = re.compile(URL_PREFIX + r"/data-collections/(\d+)\?appendComment=true$")
POSITION_RE = re.compile(URL_PREFIX + r"/data-collections/(\d+)/position$")
GRID_RE = re.compile(URL_PREFIX + r"/data-collections/(\d+)/grids$")


@dataclasses.dataclass
class ExpeyeDCRequestInfo:
    dcid: int
    url: str
    body: dict


def _mock_ispyb_conn(dcgid, dcids, giids):
    def create_or_update_dcg_response(status, request):
        return (
            status,
            {},
            json.dumps(
                {
                    "dataCollectionGroupId": dcgid,
                }
            ),
        )

    it_dc_id = iter(dcids)

    def create_dc_response(request):
        requested_dcg_id = int(DCS_RE.match(request.path_url)[2])  # type: ignore
        assert requested_dcg_id == dcgid
        return (
            201,
            {},
            json.dumps(
                {
                    "dataCollectionId": next(it_dc_id),  # type: ignore
                    "dataCollectionGroupId": dcgid,
                }
            ),
        )

    def update_dc_response(pattern, request):
        requested_dc_id = int(pattern.match(request.path_url)[2])  # type: ignore
        assert requested_dc_id in dcids
        return (
            200,
            {},
            json.dumps(
                {"dataCollectionId": requested_dc_id, "dataCollectionGroupId": dcgid}
            ),
        )

    def create_position_response(request):
        requested_dc_id = int(POSITION_RE.match(request.path_url)[2])  # type: ignore
        assert requested_dc_id in dcids
        return (201, {}, json.dumps({}))

    it_grid_info_id = iter(giids)

    def create_grid_response(request):
        requested_dc_id = int(GRID_RE.match(request.path_url)[2])  # type: ignore
        assert requested_dc_id in dcids
        return (201, {}, json.dumps({"gridInfoId": next(it_grid_info_id)}))  # type: ignore

    class ExpeyeRequestsUtil:
        def __init__(self, mock_req: responses.RequestsMock):
            self.mock_req = mock_req
            for pattern, callback in {
                DCGS_RE: partial(create_or_update_dcg_response, 201),
                DCS_RE: create_dc_response,
                POSITION_RE: create_position_response,
                GRID_RE: create_grid_response,
            }.items():
                self.mock_req.add_callback(
                    responses.POST,
                    pattern,
                    callback=callback,
                    content_type="application/json",
                )

            for pattern, callback in {
                DC_RE: partial(update_dc_response, DC_RE),
                DC_COMMENT_RE: partial(update_dc_response, DC_COMMENT_RE),
                DCG_RE: partial(create_or_update_dcg_response, 200),
            }.items():
                self.mock_req.add_callback(
                    responses.PATCH,
                    pattern,
                    callback=callback,
                    content_type="application/json",
                )

        def calls_for(self, pattern: str | re.Pattern):
            if not isinstance(pattern, re.Pattern):
                return [c for c in self.mock_req.calls if c.request.url == pattern]
            else:
                return [c for c in self.mock_req.calls if pattern.match(c.request.url)]

        def dc_calls_for(self, pattern: re.Pattern):
            return [
                ExpeyeDCRequestInfo(
                    dcid=int(pattern.match(c.request.url)[2]),  # type: ignore
                    url=c.request.url,  # type: ignore
                    body=json.loads(c.request.body),  # type: ignore
                )
                for c in self.calls_for(pattern)
            ]

        def match(self, req: PreparedRequest, pattern: re.Pattern, idx: int) -> str:
            matcher = pattern.match(req.url)
            assert matcher
            return matcher[idx]

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rq_mock:
        yield ExpeyeRequestsUtil(rq_mock)


@pytest.fixture
def mock_ispyb_conn(request):
    dcg_id = getattr(request, "param", {}).get("dcg_id", TEST_DATA_COLLECTION_GROUP_ID)
    yield from _mock_ispyb_conn(
        dcg_id,
        TEST_DATA_COLLECTION_IDS,
        TEST_GRID_INFO_IDS,
    )


@pytest.fixture
def mock_ispyb_conn_multiscan():
    yield from _mock_ispyb_conn(
        TEST_DATA_COLLECTION_GROUP_ID,
        list(range(12, 24)),
        list(range(56, 68)),
    )
