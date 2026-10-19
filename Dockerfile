# ==============================================================================
# Multi-stage Dockerfile para el microservicio de persistencia (FastAPI + uv)
# ==============================================================================

# ------------------------------------------------------------------------------
# Etapa 1: Builder (resolución e instalación de dependencias de producción)
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /build

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar exclusivamente dependencias de producción (sin dev) en .venv
RUN uv sync --frozen --no-dev --no-editable

# ------------------------------------------------------------------------------
# Etapa 2: Runtime (imagen final ligera y segura para producción)
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Crear usuario no root por seguridad (UID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/bash -m appuser

# Copiar el entorno virtual de dependencias de producción compilado en el builder
COPY --from=builder /build/.venv /app/.venv

# Configurar PATH para usar el entorno virtual
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copiar el código fuente, las migraciones de Alembic y el script de entrypoint
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY entrypoint.sh /app/entrypoint.sh

# Asegurar permisos de ejecución para entrypoint y usuario no root
RUN chmod +x /app/entrypoint.sh && \
    chown -R appuser:appuser /app

# Cambiar a usuario no root
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
