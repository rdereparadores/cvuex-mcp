from urllib.parse import parse_qsl

import httpx
import pytest

from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, encode_params
from cvuex_mcp.sites import Site

SITE = Site(key="test", name="Test", url="https://moodle.example")


def client_answering(payload, requests: list[httpx.Request] | None = None) -> MoodleClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return MoodleClient(SITE, "tok", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_encode_params_flattens_nested_values():
    params = {"ids": [1, 2], "options": [{"name": "x", "value": True}], "q": "a b"}
    assert encode_params(params) == {
        "ids[0]": "1",
        "ids[1]": "2",
        "options[0][name]": "x",
        "options[0][value]": "1",
        "q": "a b",
    }


async def test_call_sends_token_function_and_params():
    requests: list[httpx.Request] = []
    async with client_answering({"ok": True}, requests) as moodle:
        assert await moodle.call("core_x", courseids=[5]) == {"ok": True}

    [request] = requests
    assert str(request.url) == "https://moodle.example/webservice/rest/server.php"
    assert dict(parse_qsl(request.content.decode())) == {
        "wstoken": "tok",
        "wsfunction": "core_x",
        "moodlewsrestformat": "json",
        "courseids[0]": "5",
    }


async def test_call_raises_moodle_errors():
    error = {"exception": "moodle_exception", "errorcode": "nopermission", "message": "No"}
    async with client_answering(error) as moodle:
        with pytest.raises(MoodleError) as caught:
            await moodle.call("core_x")
    assert caught.value.errorcode == "nopermission"
    assert not isinstance(caught.value, InvalidTokenError)


async def test_call_distinguishes_invalid_token():
    error = {"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "No"}
    async with client_answering(error) as moodle:
        with pytest.raises(InvalidTokenError):
            await moodle.call("core_x")


async def test_shared_http_client_is_not_closed():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
    async with MoodleClient(SITE, "tok", http=http):
        pass
    assert not http.is_closed
    await http.aclose()


async def test_own_http_client_is_closed():
    moodle = MoodleClient(SITE, "tok")
    async with moodle:
        pass
    assert moodle._http.is_closed
