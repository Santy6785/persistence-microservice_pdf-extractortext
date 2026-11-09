# Registro de Decisiones de Arquitectura (ADR) - Microservicio `persistence`

Este documento registra las decisiones clave de diseño, arquitectura y operabilidad adoptadas para el microservicio `persistence`, alineadas con los principios de Clean Architecture, robustez ante fallos y las directrices del sistema distribuido de extracción de texto de PDFs.

---

## D-1: Elección de MongoDB como Motor de Persistencia

* **Estado:** Aceptado.
* **Contexto:** Inicialmente se evaluó y prototipó PostgreSQL con SQLAlchemy. Sin embargo, los requerimientos del dominio (documentos con texto extraído de longitud variable, estructura de metadatos libre y esquema JSON BSON natural) favorecen un almacén orientado a documentos.
* **Decisión:** Se utiliza **MongoDB 7** con el driver oficial asíncrono **PyMongo** (`AsyncMongoClient`).
* **Justificación:**
  1. **Naturaleza del modelo de datos:** Los documentos extraídos son agregados autosuficientes que no requieren joins relacionales.
  2. **Flexibilidad de metadatos:** El campo `metadata` se almacena como documento embebido nativo en BSON sin necesidad de configuraciones dialectales especiales como `JSONB`.
  3. **Garantía atómica de unicidad:** La unicidad estricta del `checksum_sha256` se garantiza mediante un índice único en el motor (`uq_checksum_sha256`), eliminando condiciones de carrera (TOCTOU).
  4. **Paginación determinista:** Soporte directo con índice compuesto `(created_at DESC, _id ASC)` (`ix_created_at_id`).
  5. **Manejo del límite BSON:** El límite de documento de MongoDB es de 16 MB. Para evitar errores en runtime, el servicio impone a nivel HTTP un límite preventivo estricto de 14 MB (`MAX_PAYLOAD_SIZE_BYTES=14680064`), traduciendo cualquier excedente a error HTTP 413 (`DocumentTooLargeError`).

---

## D-2: Redacción Estricta de `extracted_text` en Trazabilidad y Logs (`/trace`)

* **Estado:** Aceptado.
* **Contexto:** Los documentos procesados pueden contener datos personales, información confidencial o texto masivo que satura los buffers de logging y herramientas de observabilidad.
* **Decisión:**
  1. El endpoint de diagnóstico `/trace` (y cualquier middleware/logger del sistema) aplica **redacción automática y obligatoria** sobre el campo `extracted_text`.
  2. Ningún log estructurado, traza de ejecución o respuesta de error (4xx / 5xx) expone el contenido textual del PDF. Solo se registran metadatos seguros: `document_id`, `checksum_sha256`, `filename`, `text_length` (longitud en caracteres) y códigos de evento.
  3. Cuando la respuesta de la petición capturada tiene código de estado >=400, el cuerpo de la petición **no se guarda** (se reemplaza por una nota de omisión) para evitar filtrar datos sensibles (p. ej. campos desconocidos con texto largo en un 422).

---

## D-3: Semántica de Actualización (`PATCH`) y Campos Modificables

* **Estado:** Aceptado.
* **Contexto:** Se requiere permitir la actualización de metadatos o corrección de nombres de archivo sin comprometer la integridad histórica ni la relación unívoca entre el PDF procesado y su texto.
* **Decisión:**
  1. El método de actualización admitido es exclusivamente `PATCH /api/v1/documents/{id}`.
  2. **Campos estrictamente modificables:**
     * `filename` (string, 1-255 caracteres).
     * `metadata` (objeto JSON libre; se aplica fusión superficial/merge o reemplazo según el contrato).
  3. **Campos estrictamente inmutables (WORM - Write Once, Read Many):**
     * `id` (identificador único persistido en `_id`).
     * `checksum_sha256` (huella criptográfica del binario original).
     * `extracted_text` (el texto extraído es inmutable; si el texto cambia, corresponde a otro archivo o a una nueva extracción con otro checksum).
     * `page_count` y `file_size_bytes` (atributos intrínsecos del PDF original).
     * `created_at` (timestamp original de persistencia).
  4. Cualquier intento de enviar campos inmutables en el cuerpo del `PATCH` es rechazado con error `422 Unprocessable Entity` (`extra="forbid"`).

---

## D-4 / Nota de Confianza del Checksum

* **Estado:** Aceptado.
* **Contexto:** En la arquitectura distribuida previa se discutió si el microservicio de persistencia debía validar o recalcular el hash criptográfico del PDF.
* **Decisión y Nota de Confianza:**
  1. **Persistencia NO calcula ni recalcula checksums:** El servicio `persistence` recibe texto plano y metadatos; no tiene acceso al archivo binario original del PDF ni realiza operaciones de hashing criptográfico sobre el contenido.
  2. **Cálculo delegado al orquestador / extractor:** Es responsabilidad exclusiva del microservicio que procesa el PDF original (orquestador o extractor) calcular el `checksum_sha256` de 64 caracteres hexadecimales en minúsculas.
  3. **Nota de confianza:** El microservicio `persistence` **confía plenamente en la veracidad del checksum recibido** en la petición.
  4. **Garantía atómica de unicidad:** La integridad del sistema no depende de comprobaciones previas en memoria ("buscar y luego insertar"). La unicidad la garantiza el **índice único a nivel de motor de base de datos** (`uq_checksum_sha256`). Si dos peticiones concurrentes envían el mismo checksum, el motor de base de datos genera una colisión atómica (`DuplicateKeyError`), la cual es interceptada por el repositorio y convertida a una excepción de dominio `DocumentAlreadyExistsError`, respondiendo HTTP `409 Conflict` con el `existing_id`.

---

## D-5: Convenciones de Observabilidad, Métricas y Logging

* **Estado:** Aceptado.
* **Contexto:** Alineación con los estándares globales del sistema y las decisiones adoptadas en el frontend (D-5).
* **Decisión:**
  1. **Logging estructurado:** Emisión de logs exclusivamente en formato JSON por `stdout`.
  2. **Propagación de contexto:** Cada petición HTTP debe contar con un identificador de correlación `request_id` (propagado vía cabecera `X-Request-ID` o generado automáticamente mediante UUID v4 en `RequestIdMiddleware`).
  3. **Estructura uniforme de eventos:** Los logs incluyen `timestamp` (UTC ISO-8601), `level`, `service: "persistence"`, `request_id`, `event` y atributos específicos no sensibles.
  4. **Formato uniforme de error (`ErrorEnvelope`):** Todas las respuestas de error en la API v1 cumplen con la estructura estandarizada:
     ```json
     {
       "error": {
         "code": "CODIGO_ERROR",
         "message": "Descripción legible",
         "details": {},
         "request_id": "uuid-o-trace",
         "timestamp": "2026-11-04T14:00:00Z"
       }
     }
     ```

   5. **Métricas Prometheus (/metrics):** El formato de texto es \	ext/plain; version=0.0.4\, escrito a mano sin depender de \prometheus_client\. Las métricas son por proceso (memoria), no hay autenticación (solo red interna) y Traefik no debe enrutar \/metrics\ al exterior. La etiqueta oute\ usa la plantilla de ruta (nunca ids, checksums o filenames). \/metrics\ no se cuenta a sí mismo; \/health/*\ sí. El ping a MongoDB (\mongodb_up\) usa un timeout corto configurable (\MONGODB_PING_TIMEOUT_MS\, default 2000 ms); si falla, \mongodb_up\ queda en 0 y el endpoint sigue respondiendo 200.
