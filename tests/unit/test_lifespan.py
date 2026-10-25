import json
import logging

from fastapi import FastAPI

import app.infrastructure.database.connection as connection
from app.main import lifespan


async def test_lifespan_creates_and_closes_mongo_client(monkeypatch, caplog):
    """El lifespan crea el cliente singleton de Mongo al entrar y lo cierra al salir."""
    caplog.set_level(logging.INFO)

    class FakeClient:
        closed = False

        async def close(self):
            self.closed = True

    fake = FakeClient()

    monkeypatch.setattr(connection, "get_client", lambda: fake)
    monkeypatch.setattr(connection, "_client", fake)

    async def fake_close():
        fake.closed = True
        connection._client = None

    monkeypatch.setattr(connection, "close_client", fake_close)

    async with lifespan(FastAPI()):
        assert fake.closed is False

    assert fake.closed is True
    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    assert any(entry["event"] == "mongodb_client_closed" for entry in logs), logs
