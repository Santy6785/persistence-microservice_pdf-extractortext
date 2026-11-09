# Contrato de Endpoint: Metrics (Métricas Prometheus)

Expone las métricas del microservicio en formato de texto de Prometheus
(text/plain; version=0.0.4), escritas a mano sin depender de
`prometheus_client`.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/metrics`
* **Código HTTP de éxito:** `200 OK`
* **Content-Type:** `text/plain; version=0.0.4; charset=utf-8`

---

## 2. Entrada (Request)

El endpoint no acepta parámetros de consulta ni cuerpo.

---

## 3. Salida (Response)

El cuerpo contiene las métricas en formato de texto de Prometheus. Ejemplo:

```text
# HELP http_requests_total http_requests_total
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/health/live",status="200"} 3.0
http_requests_total{method="GET",route="/api/v1/documents/{id}",status="200"} 2.0
http_requests_total{method="GET",route="unmatched",status="404"} 1.0
# HELP http_request_duration_seconds http_request_duration_seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",route="/health/live",le="0.005"} 1.0
http_request_duration_seconds_bucket{method="GET",route="/health/live",le="+Inf"} 1.0
http_request_duration_seconds_count{method="GET",route="/health/live"} 1.0
http_request_duration_seconds_sum{method="GET",route="/health/live"} 0.003
# HELP mongodb_up mongodb_up
# TYPE mongodb_up gauge
mongodb_up 1.0
```

---

## 4. Métricas expuestas

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `http_requests_total` | Counter | Total de peticiones HTTP, etiquetado por `method`, `route` y `status`. |
| `http_request_duration_seconds` | Histograma | Duración de las peticiones en segundos, etiquetado por `method` y `route`. |
| `mongodb_up` | Gauge | 1 si el ping a MongoDB respondió, 0 si falló o hubo timeout. |

---

## 5. Reglas de etiquetado

* `route` es la **plantilla de ruta** (p. ej. `/api/v1/documents/{id}`), nunca
  la ruta cruda ni valores reales de `id`, `checksum` o `filename`.
* Las rutas sin match se etiquetan como `unmatched`.
* `/metrics` no se cuenta a sí mismo.
* Los endpoints `/health/*` sí se cuentan.

---

## 6. Redacción y privacidad

Las etiquetas no contienen datos sensibles. Nunca se exponen `extracted_text`,
`Authorization`, `Cookie` ni cuerpos de petición en las métricas.

---

## 7. Códigos de Estado

| Código HTTP | Descripción |
|-------------|-------------|
| **`200 OK`** | Métricas devueltas correctamente. Siempre devuelve 200, incluso si MongoDB no responde (`mongodb_up 0`). |

---

## 8. Operatividad

* Cada réplica del servicio mantiene **sus propios contadores en memoria**;
  no hay compartición entre réplicas.
* `/metrics` **no tiene autenticación propia**: se asume que solo es accesible
  desde la red interna. Traefik (u otro proxy frontal) no debe enrutar
  `/metrics` al exterior.
* El ping a MongoDB usa un timeout corto configurable
  (`MONGODB_PING_TIMEOUT_MS`, default 2000 ms). Si el ping no responde a
  tiempo, `mongodb_up` queda en 0 y el endpoint sigue respondiendo 200.
