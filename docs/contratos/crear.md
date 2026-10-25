# Contrato: crear documento (borrador pendiente de validar con el equipo)

> **Estado:** borrador derivado de la entidad `Document` y los esquemas Pydantic existentes.
> Pendiente de validación con el equipo antes de considerarlo definitivo.

Endpoint: `POST /api/v1/documents`
Código de éxito: `201 Created`

## Cuerpo de la petición (`DocumentCreateRequest`)

| Campo | Tipo | Requerido | Restricciones | Notas |
|-------|------|-----------|---------------|-------|
| `checksum_sha256` | string | sí | 64 caracteres hexadecimales `[a-f0-9]{64}` | Se normaliza a minúsculas |
| `filename` | string | sí | 1–255 caracteres | Nombre original del archivo |
| `extracted_text` | string | sí | — | Texto completo extraído del PDF |
| `page_count` | integer | no | ≥ 0 | Cantidad de páginas |
| `file_size_bytes` | integer | no | ≥ 0 | Tamaño en bytes del archivo original |
| `metadata` | object | no | — | Metadatos libres (default `{}`) |

Campos desconocidos son rechazados (`extra="forbid"`).

## Respuesta (`DocumentResponse`)

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | string | UUID v4 generado por el servicio; se persiste como `_id` en MongoDB |
| `checksum_sha256` | string | Normalizado a minúsculas; índice único en MongoDB |
| `filename` | string | |
| `extracted_text` | string | Texto completo; NO se expone en listados paginados |
| `page_count` | integer | opcional |
| `file_size_bytes` | integer | opcional |
| `metadata` | object | default `{}` |
| `created_at` | datetime | Timestamp de creación (UTC) |
| `updated_at` | datetime | Timestamp de última actualización (UTC) |

## Reglas de negocio

- Unicidad estricta y atómica de `checksum_sha256`. Un duplicado devuelve `409 Conflict` con `existing_id`.
- El identificador `id` es generado por el servicio (UUID v4), no proviene del cliente.
- `extracted_text` es inmutable una vez guardado (WORM: write-once, read-many).

## Errores relevantes

| Código | HTTP | Significado |
|--------|------|-------------|
| `VALIDATION_ERROR` | 422 | Body inválido, checksum mal formado, campos desconocidos |
| `DOCUMENT_ALREADY_EXISTS` | 409 | Checksum duplicado; `details.existing_id` con el ID existente |
| `PERSISTENCE_INFRASTRUCTURE_ERROR` | 500 | Fallo de MongoDB (sin exponer secretos ni texto) |
