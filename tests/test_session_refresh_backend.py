import asyncio
from threading import Event

import pytest
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import Response

from backend.app import main


def write_request():
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/logout",
        "headers": [
            (b"cookie", f"{main.settings.session_cookie_name}=local-session".encode()),
            (b"x-csrf-token", b"local-csrf"),
        ],
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("slow_operation", ["read", "delete"])
async def test_session_io_allows_other_async_work_to_progress(monkeypatch, slow_operation):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    done = Event()
    progressed_during_io = []
    visited_endpoint = []

    def slow_io():
        loop.call_soon_threadsafe(started.set)
        progressed_during_io.append(done.wait(timeout=2))

    def read(_session_id):
        if slow_operation == "read":
            slow_io()
        return {"csrf_token": "local-csrf"}

    def delete(_session_id):
        slow_io()

    async def endpoint(_request):
        visited_endpoint.append(True)
        return Response(status_code=204)

    async def independent_work():
        await started.wait()
        done.set()

    monkeypatch.setattr(main, "read_session", read)
    monkeypatch.setattr(main, "session_expired", lambda _: slow_operation == "delete")
    monkeypatch.setattr(main, "delete_session", delete)

    response, _ = await asyncio.wait_for(
        asyncio.gather(main.csrf_middleware(write_request(), endpoint), independent_work()),
        timeout=5,
    )
    assert response.status_code == (204 if slow_operation == "read" else 401)
    assert visited_endpoint == ([True] if slow_operation == "read" else [])
    assert progressed_during_io == [True]


@pytest.mark.asyncio
async def test_session_read_dependency_failure_stays_503(monkeypatch):
    def read(_session_id):
        raise RedisError("test dependency unavailable")

    async def endpoint(_request):
        pytest.fail("dependency failure must not call the endpoint")

    monkeypatch.setattr(main, "read_session", read)
    response = await main.csrf_middleware(write_request(), endpoint)
    assert response.status_code == 503
    assert b'DEPENDENCY_UNAVAILABLE' in response.body
