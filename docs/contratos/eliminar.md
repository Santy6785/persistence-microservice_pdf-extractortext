# Contrato de Endpoint: Eliminar Documento

Permite eliminar físicamente un documento y su texto extraído de la base de datos utilizando su identificador único (UUID v4).

---

## 1. Identificación del Endpoint

* **Método HTTP:** `DELETE`
* **Ruta:** `/api/v1/documents/{id}`
* **Código HTTP de éxito:** `204 No Content`
* **Cuerpo de respuesta en éxito:** Ninguno (vacío)

---

## 2. Entrada (Request)

### Parámetros de Ruta (Path Parameters)

| Parámetro | Tipo | Requerido | Formato | Descripción |
|---|---|---|---|---|
| `id` | string | Sí | UUID v4 | Identificador único del documento a eliminar |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para observabilidad distribuida |

### Cuerpo de la Petición
* No aplica (`DELETE` sin cuerpo).

---

## 3. Salida (Response)

* **Código:** `204 No Content`
* **Headers:** `X-Request-ID`
* **Cuerpo:** Vacío.

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`204 No Content`** | — | Documento eliminado con éxito. | Sin cuerpo |
| **`404 Not Found`** | `DOCUMENT_NOT_FOUND` | No existe ningún documento con el UUID provisto. | `ErrorEnvelope` |
| **`409 Conflict`** | `DOCUMENT_CONFLICT` | *Conflicto de eliminación:* el documento está en proceso de lectura/bloqueo por una tarea administrativa crítica. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | El parámetro `{id}` no es un UUID v4 sintácticamente válido. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error durante la operación `deleteOne` en MongoDB. | `ErrorEnvelope` (sin datos sensibles) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB no accesible o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Eliminación en Base de Datos:** Se remueve el documento BSON correspondiente de la colección `documents` de MongoDB. El `checksum_sha256` queda liberado en el índice único, permitiendo volver a persistir un documento con dicho hash si fuera necesario en el futuro.
2. **Observabilidad:** Emisión de log estructurado `document_deleted` con `document_id` y `request_id`.

---

## 6. Requisitos No Funcionales

* **Idempotencia:** El primer borrado devuelve `204`. Un reintento subsiguiente con el mismo ID devuelve `404 Not Found` (comportamiento estándar REST para borrado físico).
* **Consistencia:** Eliminación atómica a nivel de documento único en MongoDB.
