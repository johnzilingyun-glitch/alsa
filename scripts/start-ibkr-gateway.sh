#!/bin/bash
# IBKR Client Portal Gateway Startup Script
# Supports both Docker mode and local Java mode
# Usage: ./scripts/start-ibkr-gateway.sh [--docker|--local]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
GATEWAY_PORT="${IBKR_GATEWAY_PORT:-5000}"
GATEWAY_DIR="${PROJECT_DIR}/clientportal"
DOCKER_IMAGE="${IBKR_DOCKER_IMAGE:-gnzsnz/ib-gateway:latest}"
CONTAINER_NAME="ibkr-gateway"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[IBKR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[IBKR]${NC} $1"; }
log_error() { echo -e "${RED}[IBKR]${NC} $1"; }

check_port() {
  if ss -tlnp 2>/dev/null | grep -q ":${GATEWAY_PORT} " || \
     lsof -i ":${GATEWAY_PORT}" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

stop_gateway() {
  log_info "Stopping IBKR Gateway..."
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  if [[ -f "${PROJECT_DIR}/.ibkr-gateway.pid" ]]; then
    kill "$(cat "${PROJECT_DIR}/.ibkr-gateway.pid")" 2>/dev/null || true
    rm -f "${PROJECT_DIR}/.ibkr-gateway.pid"
  fi
}

start_docker() {
  if ! command -v docker &>/dev/null; then
    log_error "Docker not found"
    return 1
  fi

  if ! docker image inspect "$DOCKER_IMAGE" &>/dev/null; then
    log_warn "Docker image $DOCKER_IMAGE not found locally. Pulling..."
    docker pull "$DOCKER_IMAGE" || {
      log_error "Failed to pull $DOCKER_IMAGE"
      return 1
    }
  fi

  # Stop existing container if running
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

  log_info "Starting IBKR Gateway via Docker (port $GATEWAY_PORT)..."
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${GATEWAY_PORT}:5000" \
    -e TWS_USERID="${IBKR_USER:-}" \
    -e TWS_PASSWORD="${IBKR_PASS:-}" \
    -e TRADING_MODE="${IBKR_TRADING_MODE:-paper}" \
    -e TWS_ACCEPT_INCOMING="${IBKR_ACCEPT_INCOMING:-}" \
    --restart unless-stopped \
    "$DOCKER_IMAGE"

  log_info "Container '$CONTAINER_NAME' started."
  log_info "Login at: https://localhost:${GATEWAY_PORT}"
  return 0
}

start_local() {
  if [[ ! -d "$GATEWAY_DIR" ]]; then
    log_error "Gateway not found at $GATEWAY_DIR"
    log_warn "Download from: https://download2.interactivebrokers.com/portal/clientportal.gw.zip"
    log_warn "Then extract to: $GATEWAY_DIR"
    return 1
  fi

  local run_script=""
  if [[ -f "$GATEWAY_DIR/bin/run.sh" ]]; then
    run_script="$GATEWAY_DIR/bin/run.sh"
  elif [[ -f "$GATEWAY_DIR/run.sh" ]]; then
    run_script="$GATEWAY_DIR/run.sh"
  else
    log_error "Cannot find run.sh in $GATEWAY_DIR"
    return 1
  fi

  if ! command -v java &>/dev/null; then
    log_error "Java not found. Install with: sudo apt install default-jre-headless"
    return 1
  fi

  log_info "Starting IBKR Gateway via Java (port $GATEWAY_PORT)..."
  cd "$GATEWAY_DIR"
  
  # Use custom conf if available
  local conf_file="${PROJECT_DIR}/scripts/ibkr-gateway.conf.yaml"
  if [[ -f "$conf_file" ]]; then
    cp "$conf_file" "$GATEWAY_DIR/root/conf.yaml"
  fi
  
  bash "$run_script" root/conf.yaml &
  
  local pid=$!
  echo "$pid" > "${PROJECT_DIR}/.ibkr-gateway.pid"
  cd "$PROJECT_DIR"
  
  log_info "Gateway started (PID: $pid)"
  log_info "Login at: https://localhost:${GATEWAY_PORT}"
  return 0
}

# === Main ===
MODE="${1:-auto}"

# If already running, skip (unless stopping)
if [[ "$MODE" != "--stop" && "$MODE" != "-s" && "$MODE" != "stop" ]] && check_port; then
  log_info "IBKR Gateway already running on port $GATEWAY_PORT"
  exit 0
fi

case "$MODE" in
  --docker|-d)
    start_docker
    ;;
  --local|-l)
    start_local
    ;;
  --stop|-s)
    stop_gateway
    exit 0
    ;;
  --auto|auto|"")
    # Try Docker first, then local
    if docker image inspect "$DOCKER_IMAGE" &>/dev/null 2>&1; then
      start_docker
    elif [[ -d "$GATEWAY_DIR" ]]; then
      start_local
    else
      log_warn "IBKR Gateway not available."
      log_warn "Options:"
      log_warn "  1. Pull Docker image: docker pull $DOCKER_IMAGE"
      log_warn "  2. Download gateway: curl -L https://download2.interactivebrokers.com/portal/clientportal.gw.zip -o /tmp/gw.zip && unzip /tmp/gw.zip -d $GATEWAY_DIR"
      log_warn "App will start without IBKR Gateway. Dashboard will show 'not connected'."
      exit 0
    fi
    ;;
  *)
    echo "Usage: $0 [--docker|--local|--stop|--auto]"
    exit 1
    ;;
esac

# Wait for gateway to be ready
log_info "Waiting for Gateway to be ready..."
for i in $(seq 1 15); do
  if check_port; then
    log_info "Gateway is ready! Login at https://localhost:${GATEWAY_PORT}"
    exit 0
  fi
  sleep 2
done

log_warn "Gateway started but port $GATEWAY_PORT not yet responding."
log_warn "It may take a moment to initialize. Check https://localhost:${GATEWAY_PORT}"
exit 0
