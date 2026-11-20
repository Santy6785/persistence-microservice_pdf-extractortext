# ADR-001: Formato de error compartido — ¿agregar `detail` como alias de `message`?

**Issue:** P-02  
**Fecha:** 2026-11-20  
**Decisores:** equipo del proyecto  
**Registro relacionado:** `docs/decisiones.md` (Registro de Decisiones de Arquitectura del microservicio `persistence`)

## Estado

Propuesta (pendiente de decisión del equipo).

## Contexto

El microservicio `persistence` expone un formato de error uniforme (`ErrorEnvelope`) en todas sus respuestas `4xx` y `5xx`:

```json
{
  "error": {
    "code": "CODIGO_ERROR",
    "message": "Descripción legible del error",
    "details": {},
    "request_id": "uuid-o-trace",
    "timestamp": "2026-11-04T14:00:00Z"
  }
}
```

La estructura se construye única y exclusivamente mediante `build_error_payload` en
`app/api/error_handlers.py` (línea 24), y todos los handlers de excepción pasan por ella:

| Código | Handler | Línea (`app/api/error_handlers.py`) |
|--------|---------|------------------------------------|
| 422 | `validation_exception_handler` | 50 |
| 404 | `document_not_found_handler` | 74 |
| 404 (ruta inexistente) | `http_exception_handler` | 126 |
| 409 | `document_already_exists_handler` | 86 |
| 413 | `document_too_large_handler` | 107 |
| 413 (middleware) | `RequestSizeLimitMiddleware` | `app/api/middlewares.py` 88-100 y 134-146 (usa `build_error_payload`, no construye el cuerpo a mano) |
| 503 | `persistence_infrastructure_handler` | 144 |
| 500 | `unhandled_exception_handler` | 163 |
| 404 (`/trace` sin registro) | uso directo de `build_error_payload` | `app/main.py` 91 |

El schema Pydantic que valida la respuesta está en `app/api/schemas.py`:
`ErrorDetail` (líneas 16-23) con campos `code`, `message`, `details`, `request_id`, `timestamp`;
`ErrorEnvelope` (líneas 26-29) que envuelve `error: ErrorDetail`.

Este formato está fijado por D-5, punto 6, de `docs/decisiones.md` (Estado: Aceptado).

Referencias D7/P4: citadas en la issue P-02; no se encontraron en este
repositorio (docs/decisiones.md llega hasta D-5). Origen a confirmar con
el autor de la issue. Tampoco existe un campo `detail` en la respuesta de
error; la única aparición de `detail` es `exc.detail` en `http_exception_handler` (línea 137),
que es el detalle de la excepción Starlette y se vuelca como `message`, no como campo de
respuesta.

La issue P-02 recomienda exponer `detail` como alias de `message` (Opción A), pendiente de
confirmación por el equipo.

## Opciones consideradas

### Opción A: Agregar `detail` como alias de `message` en persistence

Agregar al schema `ErrorDetail` un campo opcional `detail` que repita el valor de `message`, y
poblarlo en `build_error_payload`, de modo que la respuesta contenga ambos campos.

**Ventajas:**
- Podría ahorrarle una traducción al orquestador, a verificar según cómo consuma hoy los errores.
- Los clientes existentes que ya leen `message` no se rompen (campo adicional, no removido).

**Desventajas:**
- Duplica información (`message` y `detail` con el mismo valor), lo que puede generar confusión
  sobre cuál usar.
- Requiere cambiar el schema Pydantic (`ErrorDetail`) y el builder; si el schema lo declara
  requerido, cualquier test que construya `ErrorDetail` manualmente sin ese campo falla;
  los que pasan por `build_error_payload` no.
- Amplia el contrato de `persistence` más allá de lo que el microservicio documenta hoy.

**Archivos impactados:**
- `app/api/schemas.py` — `ErrorDetail` (agregar campo `detail`).
- `app/api/error_handlers.py` — `build_error_payload` (poblar `detail`).
- `tests/unit/test_api_schemas_and_errors.py` — `test_build_error_payload_structure` (línea 86-98) y los tests de handlers 503/500 (líneas 101-132) asercionan campos individuales; si `detail` es requerido, `ErrorEnvelope.model_validate(payload)` falla.
- `tests/http/test_documents_api.py`, `tests/integration/test_e2e_mongo_api.py`, `tests/unit/test_middlewares.py`, `tests/unit/test_trace_middleware.py` — verifican `error["code"]`, `error["message"]`, `error["details"]`, `error["request_id"]`, `error["timestamp"]`; un campo adicional no rompe estas verificaciones de campo individual, pero ninguna prueba valida el JSON completo con igualdad exacta, por lo que un campo opcional no las rompe.
- `README.md` (líneas 203-215), `docs/decisiones.md` (líneas 80-91), `docs/FASE1_DISENO.md` (líneas 86, 108) y `docs/contratos/*.md` — documentan el ejemplo JSON del `ErrorEnvelope`; deberían actualizarse para incluir `detail` si se adopta.

### Opción B: El orquestador traduce

`persistence` no cambia; el orquestador (o una capa anticorrupción) mapea `message`
hacia `detail` (o expone ambos) en su propio contrato de respuesta.

**Ventajas:**
- `persistence` conserva su contrato actual sin cambios ni duplicación de campos.
- Cero riesgo de romper pruebas existentes de `persistence` ni sus consumidores actuales.
- Cada servicio es responsable del formato que expone a sus propios clientes.

**Desventajas:**
- El orquestador debe saber que `message` de `persistence` equivale a `detail` en su contrato;
  acopla al orquestador a un campo específico de `persistence`.
- Si hay varios consumidores, cada uno debe realizar la misma traducción (duplicación de
  lógica fuera de `persistence`).

**Archivos impactados:**
- Ninguno en `persistence` (app/ ni tests/).
- Código del orquestador (fuera del alcance de este repositorio).

## Punto abierto: ubicación del campo `detail`

Si se adopta la Opción A, queda por definir en qué nivel del JSON iría `detail`:

### Opción A1: `detail` dentro de `error` (nivel anidado)

```json
{
  "error": {
    "code": "...",
    "message": "...",
    "detail": "...",
    "details": {},
    "request_id": "...",
    "timestamp": "..."
  }
}
```

**Pros:**
- Mantiene todo el contrato de error bajo la clave `error`, coherente con el diseño actual de `ErrorEnvelope`.
- Un solo objeto para consumir; el cliente sabe que todo lo relacionado al error está dentro de `error`.
- `ErrorDetail` (schema Pydantic) lo modela de forma natural como otro campo del modelo.

**Contras:**
- Aumenta el anidamiento; `message` y `detail` conviven en el mismo nivel, lo que puede generar ambigüedad sobre cuál mostrar al usuario final.
- `detail` (string) convive con `details` (objeto) en el mismo nivel: nombres casi idénticos con tipos distintos, riesgo de confusión.
- Si `detail` es una copia de `message`, hay duplicación dentro de `error`.

### Opción A2: `detail` de primer nivel (hermano de `error`)

```json
{
  "error": {
    "code": "...",
    "message": "...",
    "details": {},
    "request_id": "...",
    "timestamp": "..."
  },
  "detail": "..."
}
```

**Pros:**
- `detail` queda a la misma altura que `error`, fácil de leer sin navegar el anidamiento.
- Coincide con el formato nativo de FastAPI (`{"detail": ...}`), familiar para consumidores FastAPI.
- No contamina el objeto `error` con un campo duplicado de `message`.

**Contras:**
- Rompe la simetría actual: parte del contrato queda dentro de `error` y otra parte fuera.
- Requeriría modificar `ErrorEnvelope` para agregar un campo de primer nivel adicional a `error`.
- Los clientes que esperan que todo el error viva bajo `error` tendrían que leer también la raíz.

## Decisión

Pendiente de decisión del equipo.

## Consecuencias

- Si se elige la **Opción A**, `persistence` expone un campo adicional y se deben actualizar el
  schema, el builder, las pruebas que validan la estructura del payload y la documentación
  (README, docs/decisiones.md, docs/FASE1_DISENO.md, docs/contratos/*.md).
  Requiere actualizar o reemplazar D-5 punto 6 en docs/decisiones.md.
- Si se elige la **Opción B**, no hay cambios en este repositorio; el traslado de la
  responsabilidad recae en el orquestador y no queda documentado en el contrato de
  `persistence`.
