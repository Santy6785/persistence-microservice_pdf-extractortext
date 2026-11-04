# Contrato de Endpoint: Resume (Reanudar Tráfico)

Permite reanudar la operación normal del microservicio tras haber estado en estado de pausa o mantenimiento, volviendo a habilitar la recepción y procesamiento de solicitudes de negocio.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `POST`
* **Ruta:** `/api/v1/control/resume`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `Content-Type` | No | string | `application/json` si aplica |
| `X-Request-ID` | No | string (UUID) | Identificador de correlación |

### Cuerpo de la Petición
* No requiere cuerpo obligatorio (opcionalmente vacío `{}`).

---

## 3. Salida (Response)

### Cuerpo de Éxito (`200 OK`)

```json
{
  "status": "running",
  "accepting_traffic": true,
  "database_connected": true,
  "timestamp": "2026-11-04T14:45:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Servicio reactivado exitosamente; reanudada la aceptación de peticiones. | JSON |
| **`409 Conflict`** | `NOT_PAUSED` | El servicio ya se encontraba en estado operativo normal (`running`); no estaba pausado. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error interno al restablecer el estado del controlador de tráfico. | `ErrorEnvelope` |
| **`503 Service Unavailable`** | `DATABASE_UNAVAILABLE` | No se puede reanudar el tráfico porque la prueba de ping contra MongoDB falló al intentar reconectar. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Reapertura de Tráfico:** Restablece `is_paused = False`.
2. **Impacto en Healthcheck:** `/health/ready` vuelve a reportar `200 OK` (sujeto al ping de MongoDB), permitiendo que el balanceador reanude el enrutamiento.
3. **Observabilidad:** Emisión de log estructurado `traffic_resumed`.

---

## 6. Requisitos No Funcionales

* **Verificación Preventiva:** Antes de aceptar tráfico, el comando confirma que la conexión a MongoDB esté operativa.
* **Idempotencia:** Manejado mediante código `409` si ya está activo.
