# Contrato de Endpoint: Shutdown (Apagado Ordenado / Graceful Shutdown)

Permite iniciar un proceso de apagado ordenado (*graceful shutdown*) del contenedor o proceso del microservicio de forma programática.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `POST`
* **Ruta:** `/api/v1/control/shutdown`
* **Código HTTP de éxito:** `202 Accepted`

---

## 2. Entrada (Request)

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `Content-Type` | No | string | `application/json` si se envía cuerpo |
| `X-Request-ID` | No | string (UUID) | Identificador de correlación |

### Cuerpo de la Petición (`ControlShutdownRequest`, Opcional)

```json
{
  "grace_period_seconds": 10,
  "reason": "Reinicio planificado por actualización de imagen"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `grace_period_seconds` | integer | No | Segundos de espera para drenar peticiones activas antes de finalizar (default `10`) |
| `reason` | string | No | Motivo administrativo del apagado |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`202 Accepted`)

```json
{
  "status": "shutting_down",
  "grace_period_seconds": 10,
  "message": "Graceful shutdown initiated. Sockets will be closed.",
  "timestamp": "2026-11-04T14:50:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`202 Accepted`** | — | Proceso de apagado ordenado aceptado e iniciado en background. | JSON |
| **`400 Bad Request`** | `INVALID_PARAMETERS` | Parámetro `grace_period_seconds` negativo o no numérico. | `ErrorEnvelope` |
| **`409 Conflict`** | `SHUTDOWN_IN_PROGRESS` | El proceso de apagado ya fue solicitado y está en curso. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Fallo al programar la tarea asíncrona de apagado. | `ErrorEnvelope` |
| **`503 Service Unavailable`** | `SERVICE_SHUTTING_DOWN` | El servicio ya ha comenzado a cerrar recursos y no puede aceptar nuevas conexiones. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Rechazo de Nuevas Peticiones:** `/health/ready` y `/health/live` conmutan inmediatamente para indicar que el servicio ya no está disponible.
2. **Drenado de Conexiones:** Se aguarda el tiempo de gracia para que las transacciones en vuelo completen su ejecución en MongoDB.
3. **Liberación de Recursos:** Se ejecuta `await close_client()` para cerrar el pool de conexiones con MongoDB y se finaliza el bucle de eventos (`SIGTERM` diferido).
4. **Observabilidad:** Emisión de evento final `shutdown_initiated` y `mongodb_client_closed`.

---

## 6. Requisitos No Funcionales

* **Integridad de Datos:** Garantiza que ninguna escritura que ya haya iniciado en MongoDB quede interrumpida de forma corrupta.
* **Seguridad:** Restringido a red de gestión o infraestructura interna.
