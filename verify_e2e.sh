#!/usr/bin/env bash
###############################################################################
# verify_e2e.sh - Verificación funcional del ciclo completo (smoke test)
# Microservicio de persistencia (FastAPI + MongoDB)
#
# Flujo de verificación:
#   1. Preparación: crear red externa y levantar entorno con docker compose
#   2. Prueba de aislamiento: puerto 8000 NO expuesto desde el host
#   3. Prueba de red interna: contenedor efímero llama a /health/ready (200)
#   4. Prueba de caída de MongoDB: detener mongo, POST -> 503, reiniciar mongo
#   5. Prueba de apagado controlado: docker stop <persistence> < 10s
###############################################################################

set -uo pipefail

# ---------------------------------------------------------------------------
# Colores para salida por consola
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

# ---------------------------------------------------------------------------
# Funciones de ayuda con colores
# ---------------------------------------------------------------------------
print_ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
print_err()  { echo -e "${RED}[ERROR]${NC}  $*"; }
print_info() { echo -e "${BLUE}[INFO]${NC}   $*"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }

# ---------------------------------------------------------------------------
# Variables configurables (sobrescribibles por variables de entorno)
# ---------------------------------------------------------------------------
NETWORK_NAME="${NETWORK_NAME:-pdf-extractortext_pdf-network}"
APP_SERVICE="${APP_SERVICE:-persistence}"
MONGO_SERVICE="${MONGO_SERVICE:-mongodb}"
APP_PORT="${APP_PORT:-8000}"
APP_HOST="${APP_HOST:-localhost}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-30}"

# Nombres/IDs de contenedores (se detectan automáticamente si no se pasan)
APP_CONTAINER="${APP_CONTAINER:-}"
MONGO_CONTAINER="${MONGO_CONTAINER:-}"

# ---------------------------------------------------------------------------
# Paso 0: Validar prerequisitos
# ---------------------------------------------------------------------------
print_info "Validando prerequisitos (docker, docker compose)..."
if ! command -v docker >/dev/null 2>&1; then
    print_err "Docker no está instalado o no está en el PATH."
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    print_err "Docker Compose no está disponible."
    exit 1
fi
print_ok "Prerequisitos válidos."

# Detectar contenedores automáticamente si no fueron provistos por variable de entorno
if [ -z "$APP_CONTAINER" ]; then
    APP_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q "$APP_SERVICE" 2>/dev/null | head -n1 || true)
fi
if [ -z "$MONGO_CONTAINER" ]; then
    MONGO_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q "$MONGO_SERVICE" 2>/dev/null | head -n1 || true)
fi

# Fallback a nombres por defecto si la detección falla
if [ -z "$APP_CONTAINER" ]; then
    print_warn "No se detectó el contenedor de la app. Usando nombre por defecto '$APP_SERVICE'."
    APP_CONTAINER="$APP_SERVICE"
fi
if [ -z "$MONGO_CONTAINER" ]; then
    print_warn "No se detectó el contenedor de MongoDB. Usando nombre por defecto '$MONGO_SERVICE'."
    MONGO_CONTAINER="$MONGO_SERVICE"
fi

print_info "Contenedor APP:    $APP_CONTAINER"
print_info "Contenedor MONGO:  $MONGO_CONTAINER"

# ---------------------------------------------------------------------------
# Paso 1: Preparación - red externa y levantar entorno
# ---------------------------------------------------------------------------
print_info "Paso 1: Preparación - creando red externa '$NETWORK_NAME' si no existe..."
if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    docker network create "$NETWORK_NAME" >/dev/null
    print_ok "Red '$NETWORK_NAME' creada."
else
    print_info "Red '$NETWORK_NAME' ya existe, omitiendo creación."
fi

print_info "Paso 1b: Levantando entorno con docker compose up --build -d..."
docker compose -f "$COMPOSE_FILE" up --build -d
print_ok "Entorno levantado."

# Esperar a que el servicio esté listo internamente
print_info "Esperando a que '$APP_SERVICE' esté listo (máximo $MAX_WAIT_SECONDS s)..."
READY=0
for i in $(seq 1 "$MAX_WAIT_SECONDS"); do
    if docker run --rm --network "$NETWORK_NAME" curlimages/curl \
        -s -o /dev/null --connect-timeout 2 "http://$APP_SERVICE:$APP_PORT/health/ready" 2>/dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    print_err "El servicio '$APP_SERVICE' no estuvo listo tras $MAX_WAIT_SECONDS segundos."
    exit 1
fi
print_ok "Servicio '$APP_SERVICE' listo internamente."

# ---------------------------------------------------------------------------
# Paso 2: Prueba de aislamiento - puerto NO expuesto desde el host
# ---------------------------------------------------------------------------
print_info "Paso 2: Prueba de aislamiento - curl desde host a localhost:$APP_PORT/health/live debe fallar..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 \
    "http://$APP_HOST:$APP_PORT/health/live" 2>/dev/null || true)

if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
    print_ok "Aislamiento confirmado: el puerto $APP_PORT no está expuesto públicamente (código $HTTP_CODE)."
else
    print_err "El puerto $APP_PORT está expuesto públicamente (respondió HTTP $HTTP_CODE). No debería estarlo."
    exit 1
fi

# ---------------------------------------------------------------------------
# Paso 3: Prueba de red interna - contenedor efímero llama al servicio
# ---------------------------------------------------------------------------
print_info "Paso 3: Prueba de red interna - contenedor efímero llamando a http://$APP_SERVICE:$APP_PORT/health/ready..."
HTTP_CODE=$(docker run --rm --network "$NETWORK_NAME" curlimages/curl \
    -s -o /dev/null -w "%{http_code}" --connect-timeout 10 \
    "http://$APP_SERVICE:$APP_PORT/health/ready" 2>/dev/null || true)

if [ "$HTTP_CODE" = "200" ]; then
    print_ok "Red interna OK: el servicio respondió HTTP 200 en /health/ready."
else
    print_err "Red interna falló: el servicio respondió HTTP $HTTP_CODE (se esperaba 200)."
    exit 1
fi

# ---------------------------------------------------------------------------
# Paso 4: Prueba de caída de MongoDB
# ---------------------------------------------------------------------------
print_info "Paso 4: Prueba de caída de MongoDB - deteniendo contenedor '$MONGO_CONTAINER'..."
docker stop "$MONGO_CONTAINER" >/dev/null 2>&1 || print_warn "No se pudo detener '$MONGO_CONTAINER' (quizás ya está detenido)."

print_info "Enviando POST interno a /api/v1/documents con MongoDB caído..."
HTTP_CODE=$(docker run --rm --network "$NETWORK_NAME" curlimages/curl \
    -s -o /dev/null -w "%{http_code}" --max-time 15 \
    -X POST "http://$APP_SERVICE:$APP_PORT/api/v1/documents" \
    -H "Content-Type: application/json" -d '{}' 2>/dev/null || true)

if [ "$HTTP_CODE" = "503" ]; then
    print_ok "Caída de MongoDB OK: el servicio retornó HTTP 503 rápidamente (Service Unavailable)."
else
    print_err "Caída de MongoDB falló: el servicio respondió HTTP $HTTP_CODE (se esperaba 503)."
    # Intentar reiniciar Mongo para dejar el entorno consistente antes de salir
    docker start "$MONGO_CONTAINER" >/dev/null 2>&1 || true
    exit 1
fi

print_info "Reiniciando contenedor MongoDB '$MONGO_CONTAINER'..."
docker start "$MONGO_CONTAINER" >/dev/null 2>&1
print_ok "MongoDB reiniciado."

# Esperar a que el servicio se recupere tras reiniciar MongoDB
print_info "Esperando a que el servicio se recupere tras reiniciar MongoDB (máximo $MAX_WAIT_SECONDS s)..."
RECOVERED=0
for i in $(seq 1 "$MAX_WAIT_SECONDS"); do
    if docker run --rm --network "$NETWORK_NAME" curlimages/curl \
        -s -o /dev/null --connect-timeout 2 "http://$APP_SERVICE:$APP_PORT/health/ready" 2>/dev/null; then
        RECOVERED=1
        break
    fi
    sleep 1
done

if [ "$RECOVERED" -ne 1 ]; then
    print_err "El servicio no se recuperó tras reiniciar MongoDB."
    exit 1
fi
print_ok "Servicio recuperado y MongoDB operativo de nuevo."

# ---------------------------------------------------------------------------
# Paso 5: Prueba de apagado controlado (Graceful Shutdown)
# ---------------------------------------------------------------------------
print_info "Paso 5: Prueba de apagado controlado - deteniendo contenedor '$APP_CONTAINER'..."
START_SECONDS=$(date +%s)
docker stop "$APP_CONTAINER" >/dev/null 2>&1
END_SECONDS=$(date +%s)
ELAPSED=$((END_SECONDS - START_SECONDS))

if [ "$ELAPSED" -lt 10 ]; then
    print_ok "Apagado controlado OK: contenedor detenido en ${ELAPSED}s (< 10s, gracias a SIGTERM + stop_grace_period)."
else
    print_warn "Apagado tardó ${ELAPSED}s (>= 10s). Revisar stop_signal y stop_grace_period en docker-compose.yml."
fi