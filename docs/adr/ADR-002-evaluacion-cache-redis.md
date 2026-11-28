# ADR-002: Evaluación de Caché Redis en `persistence`

**Issue:** #21 (`[Performance] Evaluar cache Redis en Persistence y decidir con evidencia`)  
**Fecha:** 2026-11-28  
**Estado:** Aceptado — **No adoptar Redis**  
**Registro relacionado:** `docs/decisiones.md` (D-6), `scripts/benchmark_persistence.py`, Orchestrator `#56`

---

## 1. Contexto

Se evaluó la incorporación de una capa de caché distribuida con Redis delante de MongoDB 7 para acelerar consultas de lectura en `persistence` (`GET /api/v1/documents/{id}`, `GET /api/v1/documents/by-checksum/{checksum}` y `GET /api/v1/documents`).

De acuerdo con los criterios de aceptación de la Issue #21:
- Redis debe integrarse **únicamente si las mediciones empíricas justifican su beneficio** frente a la complejidad operativa añadida.
- Su adopción estaba condicionada a la coordinación y disponibilidad de una instancia externa de Redis en Orchestrator (`#56`).
- Si el benchmark no demuestra mejora significativa sobre MongoDB indexado, se debe documentar la decisión y cerrar sin introducir infraestructura innecesaria.

---

## 2. Metodología y Resultados del Benchmark

Se ejecutó `scripts/benchmark_persistence.py` sobre **MongoDB 7** (`mongo:7`) con colección sembrada de **500 documentos** heterogéneos (70% de 2 KB, 25% de 100 KB y 5% de 1 MB de `extracted_text`) y los índices productivos activos (`_id`, `uq_checksum_sha256`, `ix_created_at_id`), midiendo tiempos HTTP extremo a extremo vía FastAPI (`ASGITransport`):

| Operación medida | Iteraciones ($N$) | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (ops/s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `GET /api/v1/documents/{id}` (2 KB) | 300 | 7.647 | 7.120 | 10.861 | 13.460 | 130.7 |
| `GET /api/v1/documents/by-checksum/{sha256}` (2 KB) | 300 | 7.423 | 7.130 | 7.873 | 9.000 | 134.7 |
| `GET /api/v1/documents/{id}` (100 KB) | 300 | 9.068 | 8.738 | 10.568 | 16.234 | 110.3 |
| `GET /api/v1/documents/{id}` (1 MB) | 100 | 31.241 | 29.389 | 38.723 | 55.878 | 32.0 |
| `GET /api/v1/documents?skip&limit=20` (listado) | 300 | 13.093 | 12.492 | 16.805 | 20.259 | 76.4 |
| Serialización/deserialización JSON pura (1 MB) | 100 | 7.375 | 6.908 | 9.865 | 11.151 | 133.1 |

### Análisis técnico de las mediciones

1. **Consultas puntuales indexadas (`_id` y `checksum_sha256`):** Responden en **~7.1 ms (p50)** y **<11 ms (p95)** para documentos típicos (2 KB–100 KB), representando menos del 1% del tiempo total de procesamiento de un PDF (extracción/OCR toma cientos de milisegundos a varios segundos).
2. **Costo de serialización y memoria en documentos grandes:** Para documentos de 1 MB (y hasta el límite HTTP de 14 MB), ~7 ms corresponden solo a codificación/decodificación JSON en Python y transferencia de payload. Cachear `extracted_text` completo en Redis duplicaría el consumo de RAM respecto al caché interno WiredTiger de MongoDB sin eliminar el costo de red TCP ni deserialización.
3. **Mutabilidad e invalidación:** El endpoint `PATCH /api/v1/documents/{id}` modifica `filename` y `metadata`, y `DELETE` elimina registros. Incorporar Redis exigiría invalidación transaccional multi-clave (`doc:id:{id}` y `doc:sha256:{checksum}`), manejo de *cache stampede*, TTLs y degradación controlada ante caídas de Redis, introduciendo superficie de inconsistencia de datos.
4. **Ausencia de dependencia externa (`#56`):** No existe servidor Redis aprovisionado en `docker-compose.yml` ni en el entorno desplegado.

---

## 3. Decisión

**Se rechaza la incorporación de Redis en `persistence`.** El servicio mantiene **MongoDB 7** con sus índices en memoria (`_id`, `uq_checksum_sha256`, `ix_created_at_id`) como única capa de datos y caché interna.

---

## 4. Consecuencias y Criterios de Re-evaluación

- **Simplicidad operativa:** `persistence` no suma dependencias externas ni variables de configuración de Redis; mantiene un único punto de verdad atómico.
- **Consistencia garantizada:** Sin riesgo de lecturas obsoletas tras `PATCH` o `DELETE`.
- **Re-evaluación futura:** Solo se justificará reconsiderar caché externa si la latencia `p95` de `GET /documents/by-checksum/{sha256}` supera los **50 ms** bajo carga concurrente sostenida (>500 req/s) y existe infraestructura Redis administrada disponible en el clúster.
