# Contrato de Endpoint: Listar Documentos

Permite listar los documentos persistidos con paginación determinista mediante cursor/desplazamiento (`skip` / `limit`).

> **Regla de Privacidad y Rendimiento:** La respuesta **excluye intencionalmente el campo `extracted_text`** mediante proyección de base de datos (`{"extracted_text": 0}`). Para consultar el texto completo de un documento, debe usarse `GET /api/v1/documents/{id}`.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/api/v1/documents`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Parámetros de Consulta (Query Parameters)

| Parámetro | Tipo | Requerido | Default | Restricciones | Descripción |
|---|---|---|---|---|---|
| `skip` | integer | No | `0` | `>= 0` | Número de documentos a omitir desde el inicio del listado |
| `limit` | integer | No | `20` | `1 <= limit <= 100` | Cantidad máxima de documentos a retornar en la página actual |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para observabilidad distribuida |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`PaginatedDocumentsResponse`)

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "filename": "balance_mensual.pdf",
      "page_count": 10,
      "file_size_bytes": 524288,
      "created_at": "2026-11-04T13:00:00Z",
      "updated_at": "2026-11-04T13:00:00Z"
    }
  ],
  "total": 42,
  "skip": 0,
  "limit": 20
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `items` | array[`DocumentSummaryResponse`] | Lista de documentos de la página actual (sin `extracted_text`). |
| `total` | integer | Cantidad total absoluta de documentos almacenados en la base de datos. |
| `skip` | integer | Parámetro `skip` aplicado en la consulta. |
| `limit` | integer | Parámetro `limit` aplicado en la consulta. |

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Listado obtenido correctamente (puede contener lista vacía en `items`). | Objeto `PaginatedDocumentsResponse` |
| **`409 Conflict`** | `DOCUMENT_ALREADY_EXISTS` | *No aplica a operaciones de consulta.* Se documenta en el estándar de códigos del microservicio. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | Parámetros inválidos (ej. `skip < 0`, `limit < 1`, `limit > 100` o tipos no enteros). | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Fallo inesperado en el cursor o conteo en MongoDB. | `ErrorEnvelope` (sin datos sensibles) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB no accesible o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

* **Operación de solo lectura:** No modifica colecciones en MongoDB.
* **Observabilidad:** Log del evento con `skip`, `limit`, `total` y `request_id`.

---

## 6. Requisitos No Funcionales

* **Determinismo y Orden:** El listado está estrictamente ordenado por `(created_at DESC, _id ASC)` apoyado por el índice compuesto `ix_created_at_id`, evitando desórdenes entre páginas.
* **Consumo de Ancho de Banda y Memoria:** La exclusión de `extracted_text` previene la saturación del canal HTTP y de la memoria del cliente.
* **Idempotencia:** Seguro e idempotente (`GET`).
