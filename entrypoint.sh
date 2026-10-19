#!/bin/sh
set -e

echo "[entrypoint] Ejecutando migraciones de base de datos con Alembic..."
python -m alembic upgrade head

echo "[entrypoint] Iniciando proceso principal..."
exec "$@"
