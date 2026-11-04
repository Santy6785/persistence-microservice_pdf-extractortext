# Contrato de Endpoint: Crear Documento

Permite persistir un nuevo documento con su texto extraído y metadatos asociados tras el procesamiento exitoso de un archivo PDF.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `POST`
* **Ruta:** `/api/v1/documents`
* **Código HTTP de éxito:** `201 Created`
* **Cabecera de respuesta en éxito:** `Location: /api/v1/documents/{id}`

---

## 2. Entrada (Request)

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `Content-Type` | Sí | string | Debe ser `application/json` |
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para trazabilidad distribuida |

### Cuerpo de la Petición (`DocumentCreateRequest`)

Esquema JSON estricto (`extra="forbid"`, cualquier campo no documentado provoca error `422`).

```json
{
  "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "filename": "informe_financiero_2026.pdf",
  "extracted_text": "Texto completo extraído de las páginas del PDF...",
  "page_count": 12,
  "file_size_bytes": 1048576,
  "metadata": {
    "source": "extractor-service",
    "ocr_applied": false
  }
}
```

| Campo | Tipo | Requerido | Restricciones | Descripción |
|---|---|---|---|---|
| `checksum_sha256` | string | Sí | 64 caracteres hex `^[a-fA-F0-9]{64}$` | Hash SHA-256 del binario original. Se normaliza a minúsculas. |
| `filename` | string | Sí | 1 a 255 caracteres | Nombre original del archivo PDF procesado. |
| `extracted_text` | string | Sí | Mínimo 1 carácter | Contenido textual íntegro extraído del documento. |
| `page_count` | integer | No | `>= 0` (o `null`) | Cantidad total de páginas contabilizadas en el PDF. |
| `file_size_bytes` | integer | No | `>= 0` (o `null`) | Tamaño en bytes del archivo binario original. |
| `metadata` | object | No | Objeto JSON libre (default `{}`) | Metadatos contextuales adicionales del procesamiento. |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`DocumentResponse`)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "filename": "informe_financiero_2026.pdf",
  "extracted_text": "Texto completo extraído de las páginas del PDF...",
  "page_count": 12,
  "file_size_bytes": 1048576,
  "metadata": {
    "source": "extractor-service",
    "ocr_applied": false
  },
  "created_at": "2026-11-04T14:30:00Z",
  "updated_at": "2026-11-04T14:30:00Z"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string (UUID v4) | Identificador único global generado por el servicio (`_id` en MongoDB). |
| `checksum_sha256` | string | Hash normalizado en minúsculas. |
| `filename` | string | Nombre original del archivo. |
| `extracted_text` | string | Texto completo extraído. |
| `page_count` | integer / null | Cantidad de páginas informadas. |
| `file_size_bytes` | integer / null | Tamaño en bytes del archivo original. |
| `metadata` | object | Metadatos asociados al documento. |
| `created_at` | string (ISO-8601 UTC) | Timestamp exacto de creación. |
| `updated_at` | string (ISO-8601 UTC) | Timestamp exacto de última modificación. |

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`201 Created`** | — | Documento persistido exitosamente. Retorna cabecera `Location`. | Objeto `DocumentResponse` |
| **`400 Bad Request`** | `MALFORMED_JSON` | Payload HTTP con sintaxis JSON rota o truncada. | `ErrorEnvelope` |
| **`409 Conflict`** | `DOCUMENT_ALREADY_EXISTS` | Ya existe un documento con el mismo `checksum_sha256`. El payload incluye `existing_id` y `checksum` en `details`. | `ErrorEnvelope` |
| **`413 Content Too Large`** | `PAYLOAD_TOO_LARGE` / `DOCUMENT_TOO_LARGE` | El cuerpo excede el límite HTTP de 14 MB o el límite BSON de MongoDB de 16 MB. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | Fallo de validación Pydantic (checksum inválido, longitud, campos adicionales prohibidos). | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error interno o fallo no clasificado de infraestructura. | `ErrorEnvelope` (sin texto sensible) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB inaccesible (fallo de socket/timeout) o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Inserción en Base de Datos:** Se inserta un documento BSON en la colección `documents` de MongoDB con `_id = UUID`.
2. **Evaluación de Índice Único:** El motor valida atómicamente el índice `uq_checksum_sha256`. Si hay colisión, revierte inmediatamente sin insertar.
3. **Observabilidad:** Emisión de evento estructurado JSON por stdout: `document_created` con `document_id`, `checksum`, `filename`, `text_length` (sin exponer `extracted_text`).

---

## 6. Requisitos No Funcionales

* **Idempotencia:** No idempotente a nivel HTTP (POST). Sin embargo, la unicidad atómica por `checksum_sha256` garantiza que no puedan crearse duplicados, retornando `409 Conflict` en reintentos idénticos.
* **Seguridad y Privacidad:** `extracted_text` nunca se expone en respuestas de error 4xx/5xx ni en los logs.
* **Límite de Tamaño:** Máximo 14 MB (`14680064` bytes) evaluado preventivamente por middleware antes de parsear en memoria.
* **Trazabilidad:** Inclusión obligatoria de `request_id` en headers de respuesta (`X-Request-ID`) y en cuerpo de errores.
