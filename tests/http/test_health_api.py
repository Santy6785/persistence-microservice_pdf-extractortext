import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from app.main import create_app
from app.api.health import check_db_health


@pytest.fixture
def test_app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(test_app: FastAPI):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_live_returns_200_without_db(client: AsyncClient):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


async def test_health_ready_returns_200_when_healthy(test_app: FastAPI, client: AsyncClient):
    test_app.dependency_overrides[check_db_health] = lambda: True
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "database": "connected"}


async def test_health_ready_returns_503_when_db_unhealthy(test_app: FastAPI, client: AsyncClient):
    test_app.dependency_overrides[check_db_health] = lambda: False
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unhealthy", "database": "disconnected"}
