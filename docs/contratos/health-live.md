# Contrato de Endpoint: Health Liveness (Probe de Vida)

Provee una sonda de comprobación de vida (*liveness probe*) para Kubernetes, Docker Swarm y balanceadores de carga. Confirma exclusivamente que el proceso web ASGI/FastAPI está en ejecución y es capaz de despachar conexiones entrantes.

> **Excepción de Formato:** Al ser un probe estándar de infraestructura para orquestadores, retorna un JSON plano simple (`{"status": "alive"}`), constituyendo la única excepción al `ErrorEnvelope` de la API de negocio.

---

## 1. Identificación del Endpoint

* **Método HTTP:** `GET`
* **Ruta:** `/health/live`
* **Código HTTP de éxito:** `200 OK`

---

## 2. Entrada (Request)

* **Sin parámetros de ruta ni de consulta.**
* **Sin cuerpo de petición.**
* **Cabeceras:** Opcionalmente `X-Request-ID`.

---

## 3. Salida (Response)

### Cuerpo de Éxito

```json
{
  "status": "alive"
}
```

---

## 4. Códigos de Estado y Errores

| Código HTTP | Error Code / Mensaje | Descripción |
|---|---|---|
| **`200 OK`** | — | El proceso web está activo, sin bloqueos del bucle de eventos asyncio. |
| **`409 Conflict`** | — | *No aplica.* Documentado para estandarización de contratos. |
| **`500 Internal Server Error`** | `SERVER_ERROR` | Error crítico en el runtime de Python o en el framework web. |
| **`503 Service Unavailable`** | `SERVICE_TERMINATING` | El proceso ha recibido una señal de terminación (`SIGTERM`) y está finalizando tareas. |

---

## 5. Efectos Colaterales

* **Cero interacción con infraestructura externa:** **NO realiza consultas ni pings a MongoDB**, garantizando que un fallo en la base de datos no cause el reinicio destructivo del contenedor por parte del orquestador.

---

## 6. Requisitos No Funcionales

* **Latencia Ultra-Baja:** Tiempo de respuesta esperado $< 1 \text{ ms}$.
* **Idempotencia:** Completamente seguro e idempotente (`GET`).
* **Consumo de Recursos:** Mínimo; no asigna memoria persistente ni abre descriptores de archivos adicionales.
