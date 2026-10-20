import json
import logging

from fastapi import FastAPI

from app.api import dependencies
from app.main import lifespan


async def test_lifespan_disposes_database_engine_on_shutdown(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    class FakeEngine:
        disposed = False

        async def dispose(self):
            self.disposed = True

    engine = FakeEngine()
    monkeypatch.setattr(dependencies, "_engine", engine)

    async with lifespan(FastAPI()):
        assert engine.disposed is False

    assert engine.disposed is True
    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    assert any(entry["event"] == "database_engine_disposed" for entry in logs), (
        f"events={logs!r}, logger_level={logging.getLogger('persistence.events').level}, "
        f"propagate={logging.getLogger('persistence.events').propagate}, "
        f"disabled={logging.getLogger('persistence.events').disabled}, "
        f"enabled={logging.getLogger('persistence.events').isEnabledFor(logging.INFO)}, "
        f"disable_threshold={logging.root.manager.disable}, root_level={logging.root.level}"
    )
