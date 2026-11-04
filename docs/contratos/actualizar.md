# Contrato de Endpoint: Actualizar Documento (Parcial)

Permite actualizar parcialmente campos no estructurales de un documento existente (exclusivamente `filename` y `metadata`).

> **Regla de Inmutabilidad WORM (Decisión D-3):** Los campos `extracted_text`, `checksum_sha256`, `id`, `page_count`, `file_size_bytes` y `created_at` son **estrictamente inmutables**. Si se intenta enviar alguno de estos campos, la petición es rechazada.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `PATCH`
* **Ruta:** `/api/v1/documents/{id}`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Parámetros de Ruta (Path Parameters)

| Parámetro | Tipo | Requerido | Formato | Descripción |
|---|---|---|---|---|
| `id` | string | Sí | UUID v4 | Identificador único del documento a modificar |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `Content-Type` | Sí | string | Debe ser `application/json` |
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para observabilidad distribuida |

### Cuerpo de la Petición (`DocumentUpdateRequest`)

Esquema JSON con `extra="forbid"`. Al menos uno de los dos campos editables debe ser provisto.

```json
{
  "filename": "nuevo_nombre_archivo.pdf",
  "metadata": {
    "etiqueta": "revisado_legal",
    "departamento": "finanzas"
  }
}
```

| Campo | Tipo | Requerido | Restricciones | Descripción |
|---|---|---|---|---|
| `filename` | string | No | 1 a 255 caracteres | Nuevo nombre para el archivo. |
| `metadata` | object | No | Objeto JSON libre | Nuevos metadatos. Se actualizan por reemplazo completo del objeto `metadata`. |

Cualquier campo adicional (`checksum_sha256`, `extracted_text`, `id`, etc.) provoca error `422 Unprocessable Entity`.

---

## 3. Salida (Response)

### Cuerpo de Éxito (`DocumentResponse`)

Retorna el documento completo con los cambios aplicados y `updated_at` actualizado con el timestamp UTC actual.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "filename": "nuevo_nombre_archivo.pdf",
  "extracted_text": "Texto completo original inalterado...",
  "page_count": 10,
  "file_size_bytes": 524288,
  "metadata": {
    "etiqueta": "revisado_legal",
    "departamento": "finanzas"
  },
  "created_at": "2026-11-04T13:00:00Z",
  "updated_at": "2026-11-04T15:30:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Documento modificado exitosamente. Retorna el recurso actualizado. | Objeto `DocumentResponse` |
| **`400 Bad Request`** | `EMPTY_UPDATE_PAYLOAD` / `MALFORMED_JSON` | Cuerpo vacío o sintaxis JSON rota. | `ErrorEnvelope` |
| **`404 Not Found`** | `DOCUMENT_NOT_FOUND` | No existe ningún documento con el `{id}` provisto. | `ErrorEnvelope` |
| **`409 Conflict`** | `CONCURRENT_MODIFICATION_CONFLICT` | Conflicto de concurrencia al intentar modificar simultáneamente el mismo documento en estado bloqueado. | `ErrorEnvelope` |
| **`413 Content Too Large`** | `PAYLOAD_TOO_LARGE` | Cuerpo del `PATCH` excede el límite de tamaño establecido. | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | Violación de restricciones (ej. intentar alterar `extracted_text`, longitud inválida de `filename` o `{id}` no UUID). | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error durante la ejecución del comando `update_one` en MongoDB. | `ErrorEnvelope` (sin datos sensibles) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB no accesible o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Actualización en Base de Datos:** Modificación atómica vía `updateOne` en MongoDB sobre los campos permitidos y actualización del timestamp `updated_at`.
2. **Observabilidad:** Registro de log estructurado `document_updated` con `document_id`, `updated_fields` y `request_id`.

---

## 6. Requisitos No Funcionales

* **Idempotencia:** Métodos `PATCH` con cargas idénticas producen el mismo estado final en el recurso persistido.
* **Integridad Referencial:** Ninguna actualización puede corromper la relación criptográfica entre el texto y el checksum persistido.
