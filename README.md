# Microservicio de Persistencia (`persistence`)

Microservicio backend del sistema de extracción de texto de PDFs responsable exclusivamente de **persistir de forma durable, garantizar la integridad y unicidad estricta, y consultar el texto extraído y sus metadatos asociados**.

---

## 1. Stack Tecnológico

- **Lenguaje:** Python 3.13+
- **Framework Web:** FastAPI (asíncrono, ASGI)
- **Gestor de Paquetes y Entorno:** `uv`
- **Base de Datos:** PostgreSQL 16
- **ORM / Driver:** SQLAlchemy 2.0 (asíncrono) + `asyncpg`
- **Control de Esquema y Migraciones:** Alembic
- **Validación y Serialización:** Pydantic v2 (con `extra="forbid"`)
- **Configuración:** `pydantic-settings`
- **Testing:** Pytest, `pytest-asyncio`, `httpx`, `testcontainers`
- **Linter y Formateador:** Ruff
- **Contenedores:** Docker multi-stage (usuario no-root `appuser`)

---

## 2. Arquitectura del Proyecto

El microservicio aplica **Clean Architecture** estructurada por capas con dependencias unidireccionales:

```text
app/
├── domain/                  # Capa de Dominio pura (cero dependencias externas)
│   ├── models.py            # Entidad canónica Document (dataclass)
│   ├── repositories.py      # Interfaz abstracta DocumentRepository (ABC)
│   └── exceptions.py        # Única fuente de verdad de excepciones de negocio
├── application/             # Capa de Aplicación (casos de uso)
│   ├── dtos.py              # DTOs de entrada y salida
│   └── document_service.py  # Orquestación de reglas de negocio y UUID v4
├── infrastructure/          # Capa de Infraestructura técnica
│   ├── database/            # Conexión asíncrona y modelo DocumentORM (SQLAlchemy)
│   └── repositories/        # Implementaciones: PostgresDocumentRepository y InMemoryDocumentRepository
└── api/                     # Capa de Presentación HTTP (FastAPI)
    ├── middlewares.py       # RequestIdMiddleware y RequestSizeLimitMiddleware (413 temprano)
    ├── error_handlers.py    # Formato uniforme de error para todo el servicio
    ├── dependencies.py      # Inyección de dependencias
    ├── schemas.py           # Esquemas Pydantic v2 de entrada y salida
    └── v1/                  # Endpoints versionados (/api/v1/documents)
```

---

## 3. Configuración del Entorno

Copiar el archivo de plantilla `.env.example` a `.env`:

```bash
cp .env.example .env
```

Variables disponibles:
| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `APP_ENV` | Entorno de ejecución (`development`, `production`, `test`) | `development` |
| `APP_PORT` | Puerto de escucha HTTP | `8000` |
| `APP_HOST` | Host de enlace | `0.0.0.0` |
| `LOG_LEVEL` | Nivel de logs | `INFO` |
| `MAX_PAYLOAD_SIZE_BYTES` | Límite máximo de payload aceptado | `14680064` (14 MB; margen bajo el límite BSON de 16 MB de MongoDB) |
| `DATABASE_URL` | Cadena de conexi?n as?ncrona a PostgreSQL | Configurada mediante `.env` |

---

## 4. Instalación y Ejecución

### Prerrequisitos
Tener instalado [`uv`](https://docs.astral.sh/uv/):
```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Sincronización del entorno
```bash
uv sync
```

### Aplicar migraciones de base de datos
```bash
uv run alembic upgrade head
```

### Ejecutar en modo desarrollo
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ejecución con Docker
```bash
# Construir imagen multi-stage
docker build -t persistence:latest .

# Ejecutar contenedor
docker run -p 8000:8000 --env-file .env persistence:latest
```

Al iniciar la imagen, se ejecuta `python -m alembic upgrade head` antes de iniciar Uvicorn. Si las migraciones fallan, el contenedor no inicia el servicio.

### Entorno de desarrollo con Docker Compose
Desde el directorio `persistence`, copiar `.env.example` a `.env` y reemplazar `POSTGRES_PASSWORD` por una contraseña local:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Compose levanta PostgreSQL 16 con un volumen persistente y espera su healthcheck antes de iniciar `persistence`. El puerto publicado es el de la API (`APP_PORT`, por defecto `8000`); PostgreSQL no se publica en el host. La migración se ejecuta al iniciar cada réplica de `persistence`: no escales este servicio a varias réplicas con este esquema, porque no hay coordinación entre migradores. En despliegues con varias réplicas, ejecutá la migración una sola vez como paso previo al despliegue.

---

## 5. Estrategia y Ejecución de Pruebas

Toda la lógica fue construida siguiendo **TDD estricto**:
- **Tests unitarios:** Pruebas puras de dominio, configuración y casos de uso con repositorio en memoria.
- **Tests de contrato:** Batería compartida (`test_repository_contract.py`) ejecutada de manera idéntica contra `InMemoryDocumentRepository` y `PostgresDocumentRepository`.
- **Tests de integración:** Utilizan `testcontainers[postgres]` para levantar un contenedor efímero de PostgreSQL 16 y verificar constraints ACID reales, concurrencia con `asyncio.gather` y migraciones con Alembic. Se saltan automáticamente si Docker no está activo.
- **Tests HTTP:** Validación de contratos, middlewares, códigos de estado y manejo uniforme de errores.

### Comandos de prueba con `uv`

```bash
# 1. Ejecutar toda la suite de tests (51 tests)
uv run pytest -v

# 2. Ejecutar únicamente tests rápidos (sin base de datos real)
uv run pytest -m "not integration"

# 3. Ejecutar tests de integración contra PostgreSQL real (requiere Docker)
uv run pytest -m "integration"

# 4. Chequeo de calidad y formato con Ruff
uv run ruff check .
```

---

## 6. Contratos de la API HTTP (v1)

### Formato Uniforme de Error
Todas las respuestas de error (`4xx` y `5xx`) responden con la siguiente estructura:
```json
{
  "error": {
    "code": "STRING_IDENTIFIER",
    "message": "Descripción legible del error",
    "details": {},
    "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "timestamp": "2026-10-19T20:00:00Z"
  }
}
```
*(Nota: Los endpoints `/health/live` y `/health/ready` son la única excepción a este formato).*

### Resumen de Endpoints

| Método | Ruta | Código éxito | Descripción |
| :--- | :--- | :---: | :--- |
| `POST` | `/api/v1/documents` | `201 Created` | Persiste un nuevo documento. Normaliza `checksum_sha256` a minúsculas. Devuelve header `Location`. |
| `GET` | `/api/v1/documents/{id}` | `200 OK` | Recupera el documento y texto completo por UUID. |
| `GET` | `/api/v1/documents/by-checksum/{checksum}` | `200 OK` | Recupera el documento por hash SHA-256. |
| `GET` | `/api/v1/documents?skip=0&limit=20` | `200 OK` | Lista paginada determinista (`created_at DESC, id ASC`). **Excluye** `extracted_text`. |
| `DELETE`| `/api/v1/documents/{id}` | `204 No Content` | Elimina el documento por UUID. |
| `GET` | `/health/live` | `200 OK` | Liveness probe: confirma proceso vivo (`{"status": "alive"}`). |
| `GET` | `/health/ready` | `200 OK` / `503` | Readiness probe: verifica conexión activa a Postgres (`SELECT 1`). |

### Códigos de Error Principales
- `404 Not Found` (`DOCUMENT_NOT_FOUND` / `NOT_FOUND`): Recurso o ruta no encontrada.
- `409 Conflict` (`DOCUMENT_ALREADY_EXISTS`): Intento de registrar un checksum duplicado. Devuelve `existing_id`. **Nunca** expone `extracted_text`.
- `413 Payload Too Large` (`PAYLOAD_TOO_LARGE`): Petición rechazada si excede los 14 MB (configurable vía `MAX_PAYLOAD_SIZE_BYTES`), o si el documento BSON superaría el límite de 16 MB de MongoDB. Nunca expone `extracted_text`.
- `422 Unprocessable Entity` (`VALIDATION_ERROR`): Violación de validación (body incompleto, campos desconocidos por `extra="forbid"`, query inválida como `limit=0` o `limit>100`).
- `500 Internal Server Error` (`PERSISTENCE_INFRASTRUCTURE_ERROR` / `INTERNAL_SERVER_ERROR`): Fallo de base de datos capturado sin exponer secretos ni texto extraído.

---

## 7. Decisiones Técnicas y Pendientes con el Equipo

1. **Invocador de `persistence`:** Se asume que el **orquestador** es quien invoca a este microservicio tras recibir los datos extraídos del servicio `extractor`.
2. **Checksum SHA-256:** Calculado por el extractor a partir del stream binario del PDF. `persistence` confía en el valor recibido, lo normaliza a minúsculas y garantiza unicidad estricta atómica en base de datos.
3. **Identificador del Documento:** Generado como UUID v4 por `persistence` en el momento de la inserción.
4. **Política ante Duplicados:** `persistence` responde `409 Conflict` con el ID existente. El orquestador decide si devuelve el documento al usuario o informa la colisión.
5. **Inmutabilidad del Texto:** El texto extraído es estrictamente de solo lectura una vez guardado (WORM: *write-once, read-many*).
6. **Operación `PATCH`:** Se acordó diferir la actualización parcial de metadatos a la versión **v1.1**, manteniendo el MVP limpio e inmutable.
7. **Política de Borrado:** Implementado borrado físico (hard delete) en v1. Si el equipo requiere auditoría o GDPR detallado, se evaluará soft-delete (`deleted_at`) en v1.1.
