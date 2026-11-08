# Contrato de Endpoint: Trace (Trazabilidad y Diagnóstico)

Permite consultar los eventos de auditoría, trazabilidad y estado de procesamiento asociados a una solicitud específica mediante su `request_id`.

> **Regla de Privacidad (Decisión D-2):** El endpoint aplica **redacción estricta e innegociable de `extracted_text`**. Únicamente se exponen metadatos técnicos, longitud en caracteres (`text_length`), marcas de tiempo y códigos de resultado.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/api/v1/trace/{request_id}`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Parámetros de Ruta (Path Parameters)

| Parámetro | Tipo | Requerido | Formato | Descripción |
|---|---|---|---|---|
| `request_id` | string | Sí | UUID v4 o identificador alfanumérico seguro | Identificador único de la solicitud a auditar |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `X-Request-ID` | No | string (UUID) | Identificador de la petición actual de auditoría |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`TraceResponse`)

```json
{
  "request_id": "52132169-a0d1-47d0-91ba-8d69eb591f39",
  "service": "persistence",
  "status": "completed",
  "http_status": 201,
  "events": [
    {
      "timestamp": "2026-11-04T14:30:00.120Z",
      "event": "request_received",
      "method": "POST",
      "path": "/api/v1/documents"
    },
    {
      "timestamp": "2026-11-04T14:30:00.145Z",
      "event": "document_created",
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "filename": "documento.pdf",
      "text_length": 4520,
      "extracted_text": "[REDACTED]"
    }
  ],
  "duration_ms": 35.4
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Trazabilidad recuperada con éxito. | Objeto `TraceResponse` |
| **`404 Not Found`** | `TRACE_NOT_FOUND` | No existen registros de auditoría o eventos para el `request_id` consultado (o expiraron por TTL). | `ErrorEnvelope` |
| **`409 Conflict`** | `TRACE_CONFLICT` | *No aplica a consultas de auditoría.* Se documenta en el estándar de códigos del microservicio. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | Parámetro `request_id` vacío o con caracteres de inyección inválidos. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Fallo en el backend de registro o buffer de eventos. | `ErrorEnvelope` |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Backend de observabilidad/base de datos inaccesible o servicio en pausa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

* **Operación de solo lectura:** No altera estados del sistema ni datos de negocio.
* **Depuración Segura:** Permite a operadores diagnosticar fallos sin vulnerar el secreto de los datos contenidos en los PDFs.
* **Respuestas de error (>=400):** Cuando la respuesta de la petición capturada tiene código de estado >=400, el cuerpo de la petición **no se guarda** (se reemplaza por una nota de omisión) para evitar filtrar datos sensibles (p. ej. campos desconocidos con texto largo en un 422).

---

## 6. Requisitos No Funcionales

* **Seguridad:** Filtrado y censura obligatoria (`[REDACTED]`) de campos sensibles.
* **Idempotencia:** Idempotente y seguro (`GET`).
