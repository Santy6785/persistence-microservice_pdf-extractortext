# Contrato de Endpoint: Obtener Documento por ID

Permite consultar el detalle completo de un documento previamente persistido mediante su identificador único (UUID v4).

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/api/v1/documents/{id}`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Parámetros de Ruta (Path Parameters)

| Parámetro | Tipo | Requerido | Formato | Descripción |
|---|---|---|---|---|
| `id` | string | Sí | UUID v4 (`^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$`) | Identificador único del documento |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para trazabilidad distribuida |

### Cuerpo de la Petición
* No aplica (`GET` sin cuerpo).

---

## 3. Salida (Response)

### Cuerpo de Éxito (`DocumentResponse`)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "filename": "documento_ejemplo.pdf",
  "extracted_text": "Texto completo extraído del documento...",
  "page_count": 5,
  "file_size_bytes": 204800,
  "metadata": {
    "sistema_origen": "orquestador",
    "version": 1
  },
  "created_at": "2026-11-04T14:00:00Z",
  "updated_at": "2026-11-04T14:00:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Documento encontrado y retornado con su texto completo. | Objeto `DocumentResponse` |
| **`404 Not Found`** | `DOCUMENT_NOT_FOUND` | No existe ningún documento con el UUID especificado. | `ErrorEnvelope` |
| **`409 Conflict`** | `DOCUMENT_ALREADY_EXISTS` | *No aplica directamente a operaciones de lectura.* Documentado para estandarización del microservicio: si se produce una condición de concurrencia o estado corrupto anómalo. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | El parámetro `{id}` en la ruta no cumple con el formato UUID válido. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error inesperado durante la lectura o deserialización en MongoDB. | `ErrorEnvelope` (sin texto sensible) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB no alcanzable (timeout de conexión) o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

* **Operación de solo lectura:** No modifica colecciones ni documentos en MongoDB.
* **Observabilidad:** Registro de acceso en log estructurado con `request_id`, `document_id` y tiempo de ejecución.

---

## 6. Requisitos No Funcionales

* **Idempotencia:** Completamente idempotente y seguro (método `GET`).
* **Rendimiento:** Acceso por clave primaria directa `_id` en MongoDB con complejidad esperada $O(1)$.
* **Privacidad:** `extracted_text` se transmite exclusivamente en el cuerpo de respuesta 200 cifrado por TLS, nunca en logs o trazas.
