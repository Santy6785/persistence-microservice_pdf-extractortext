# Contrato de Endpoint: Health Readiness (Probe de Disponibilidad)

Provee una sonda de comprobación de preparación (*readiness probe*) para orquestadores y balanceadores de carga. Determina si el microservicio está en condiciones operativas de recibir tráfico de negocio verificando la conectividad activa hacia MongoDB.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/health/ready`
* **Código HTTP de éxito:** `200 OK`
* **Código HTTP en degradación/fallo:** `503 Service Unavailable`

---

## 2. Entrada (Request)

* **Sin parámetros de ruta ni de consulta.**
* **Sin cuerpo de petición.**
* **Cabeceras:** Opcionalmente `X-Request-ID`.

---

## 3. Salida (Response)

### Cuerpo de Éxito (`200 OK`)

```json
{
  "status": "ready",
  "database": "connected"
}
```

### Cuerpo en Falla de Base de Datos (`503 Service Unavailable`)

```json
{
  "status": "unhealthy",
  "database": "disconnected"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Estado | Descripción |
|---|---|---|
| **`200 OK`** | `ready` | Conexión activa y respuesta positiva del comando `ping` en MongoDB. Apto para recibir tráfico. |
| **`409 Conflict`** | — | *No aplica.* Documentado para alineación del catálogo de endpoints. |
| **`500 Internal Server Error`** | `error` | Fallo de ejecución no capturado al evaluar dependencias. |
| **`503 Service Unavailable`** | `unhealthy` | MongoDB no responde, timeout en socket, autenticación fallida o servicio en pausa administrativa (`pause`). El orquestador retira el pod/contenedor del balanceador. |

---

## 5. Efectos Colaterales

1. **Comando Administrativo en Base de Datos:** Ejecuta `await client.admin.command("ping")` utilizando el cliente singleton asíncrono.
2. **Observabilidad:** Si la prueba falla, emite un log de advertencia estructurado (`database_health_check_failed`) sin propagar excepciones al caller.

---

## 6. Requisitos No Funcionales

* **Timeout Estricto:** La verificación está sujeta a `serverSelectionTimeoutMS` (default 5000 ms) para evitar el bloqueo indefinido de la sonda.
* **Idempotencia:** Seguro e idempotente (`GET`).
* **Protección de Tráfico:** Permite que Kubernetes no enrute tráfico a una instancia cuya base de datos se encuentra momentáneamente saturada o desconectada.
