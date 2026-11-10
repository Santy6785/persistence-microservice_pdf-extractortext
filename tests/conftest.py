"""Fixtures globales de la suite de tests."""

import logging

import pytest

from app.config import get_settings
from app.observability import EVENT_LOGGER


@pytest.fixture(autouse=True)
def reset_test_logging_state():
    """Aísla el estado de logging entre tests.

    Limpia el cache de get_settings() para que configure_logging() re-lea
    las variables de entorno, y resetea EVENT_LOGGER a un estado conocido
    (nivel DEBUG, sin handlers extra) para evitar que un test file previo
    (p. ej. test_log_level_ciclo4.py con LOG_LEVEL=error) deje el nivel
    en ERROR y filtre los logs INFO de los tests de otros archivos.
    """
    original_level = EVENT_LOGGER.level
    original_propagate = EVENT_LOGGER.propagate
    original_handlers = list(EVENT_LOGGER.handlers)

    get_settings.cache_clear()

    EVENT_LOGGER.setLevel(logging.DEBUG)
    EVENT_LOGGER.propagate = True
    for h in list(EVENT_LOGGER.handlers):
        EVENT_LOGGER.removeHandler(h)

    yield

    EVENT_LOGGER.setLevel(original_level)
    EVENT_LOGGER.propagate = original_propagate
    for h in list(EVENT_LOGGER.handlers):
        EVENT_LOGGER.removeHandler(h)
    for h in original_handlers:
        EVENT_LOGGER.addHandler(h)
