# Contrato de Endpoint: Buscar Documento por Checksum

Permite recuperar el documento y su texto extraído a partir de la huella digital criptográfica SHA-256 del PDF original. Utilizado por el orquestador para verificar si un archivo ya fue procesado previamente.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/api/v1/documents/by-checksum/{checksum}`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Parámetros de Ruta (Path Parameters)

| Parámetro | Tipo | Requerido | Formato | Descripción |
|---|---|---|---|---|
| `checksum` | string | Sí | 64 caracteres hex `^[a-fA-F0-9]{64}$` | Hash SHA-256 del binario original. La API normaliza a minúsculas antes de consultar. |

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `X-Request-ID` | No | string (UUID) | Identificador de correlación para observabilidad |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`DocumentResponse`)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "filename": "archivo_original.pdf",
  "extracted_text": "Texto completo extraído...",
  "page_count": 8,
  "file_size_bytes": 450120,
  "metadata": {},
  "created_at": "2026-11-04T12:00:00Z",
  "updated_at": "2026-11-04T12:00:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Documento encontrado para el checksum consultado. | Objeto `DocumentResponse` |
| **`404 Not Found`** | `DOCUMENT_NOT_FOUND` | No existe ningún documento con el checksum proporcionado. | `ErrorEnvelope` |
| **`409 Conflict`** | `DOCUMENT_ALREADY_EXISTS` | *No aplica a lecturas.* Estandarizado en el catálogo: un duplicado solo se manifiesta en escrituras (`POST`). | `ErrorEnvelope` |
| **`422 Unprocessable Entity`** | `VALIDATION_ERROR` | El parámetro `{checksum}` no cumple con el formato exacto de 64 caracteres hexadecimales. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error de consulta o deserialización en MongoDB. | `ErrorEnvelope` (sin texto sensible) |
| **`503 Service Unavailable`** | `SERVICE_UNAVAILABLE` | Base de datos MongoDB no accesible o servicio en pausa operativa. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

* **Operación de solo lectura:** No modifica la base de datos.
* **Observabilidad:** Emisión de log con `checksum` (anónimo y seguro) y `request_id`.

---

## 6. Requisitos No Funcionales

* **Idempotencia:** Idempotente y seguro (`GET`).
* **Rendimiento:** Indexación directa mediante el índice único `uq_checksum_sha256` en MongoDB con tiempo de respuesta esperado $< 5 \text{ ms}$.
* **Normalización:** La comparación es case-insensitive gracias a la normalización a minúsculas (`lowercase`) en la capa API.
