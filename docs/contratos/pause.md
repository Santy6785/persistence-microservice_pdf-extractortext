# Contrato de Endpoint: Pause (Pausar Tráfico / Drenado)

Permite suspender temporalmente la aceptación de nuevas peticiones de negocio en el microservicio (modo de mantenimiento o drenado de conexiones antes de un despliegue).

---

## 1. Identificación del Endpoint

* **Método HTTP:** `POST`
* **Ruta:** `/api/v1/control/pause`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

### Cabeceras (Headers)

| Cabecera | Requerido | Tipo | Descripción |
|---|---|---|---|
| `Content-Type` | No | string | `application/json` si se envía cuerpo |
| `X-Request-ID` | No | string (UUID) | Identificador de correlación |

### Cuerpo de la Petición (`ControlPauseRequest`, Opcional)

```json
{
  "reason": "Mantenimiento programado de réplica de MongoDB",
  "drain_timeout_seconds": 15
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `reason` | string | No | Motivo administrativo de la pausa operativa |
| `drain_timeout_seconds` | integer | No | Tiempo máximo de gracia para drenar peticiones activas (default `10`) |

---

## 3. Salida (Response)

### Cuerpo de Éxito (`200 OK`)

```json
{
  "status": "paused",
  "draining": true,
  "active_requests": 2,
  "timestamp": "2026-11-04T14:40:00Z"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code | Descripción | Formato de Error |
|---|---|---|---|
| **`200 OK`** | — | Servicio puesto en estado pausado con éxito. | JSON |
| **`400 Bad Request`** | `INVALID_PARAMETERS` | Parámetros de timeout inválidos. | `ErrorEnvelope` |
| **`409 Conflict`** | `ALREADY_PAUSED` | El servicio ya se encuentra actualmente en estado de pausa. | `ErrorEnvelope` |
| **`500 Internal Server Error`** | `PERSISTENCE_INFRASTRUCTURE_ERROR` | Error interno al conmutar el estado del circuito de tráfico. | `ErrorEnvelope` |
| **`503 Service Unavailable`** | `SERVICE_PAUSED` | *Comportamiento derivado:* Tras la pausa, las peticiones entrantes a `/api/v1/documents` responden 503 hasta que se ejecute `resume`. | `ErrorEnvelope` |

---

## 5. Efectos Colaterales

1. **Conmutación de Bandera de Tráfico:** El servicio activa la compuerta de drenado (`is_paused = True`).
2. **Impacto en Healthcheck:** El endpoint `/health/ready` comienza a devolver `503 Service Unavailable`, provocando que el balanceador/ingress deje de enviarle nuevas solicitudes.
3. **Observabilidad:** Emisión de log estructurado `traffic_paused` con `reason` y `active_requests`.

---

## 6. Requisitos No Funcionales

* **Seguridad:** Endpoint de control accesible únicamente a través de red interna o con token de infraestructura.
* **Cierre no destructivo:** Las peticiones en vuelo tienen un tiempo de gracia para finalizar antes de cortar conexiones.
