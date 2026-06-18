#!/usr/bin/env bash
# Agentic Takım bootstrap — `make setup` / `make setup-full` tarafından çağrılır.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# .env, interpolasyon için --env-file ile verilir (compose, .env'i compose
# dosyasının dizininde arar; bizimki repo kökünde). .env, setup'ta oluşturulur.
COMPOSE="docker compose -f infra/compose/docker-compose.yml --env-file .env"

log()  { printf "\033[36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m! %s\033[0m\n" "$*"; }
die()  { printf "\033[31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then ok "$1 bulundu ($($1 --version 2>&1 | head -1))"; else warn "$1 BULUNAMADI — $2"; MISSING=1; fi
}

doctor() {
  log "Ön-koşullar kontrol ediliyor..."
  MISSING=0
  check_cmd docker "https://docs.docker.com/get-docker/"
  docker compose version >/dev/null 2>&1 && ok "docker compose bulundu" || { warn "docker compose YOK"; MISSING=1; }
  check_cmd node "https://nodejs.org veya mise/asdf"
  check_cmd python3 "https://www.python.org"
  check_cmd pnpm "npm i -g pnpm"
  check_cmd uv "https://docs.astral.sh/uv/"
  if [ "${MISSING:-0}" -ne 0 ]; then
    die "Bazı ön-koşullar eksik. Docker zorunlu; node/python/pnpm/uv yerel geliştirme için önerilir."
  fi
  ok "Tüm ön-koşullar hazır."
}

setup() {
  local mode="${1:-core}"
  doctor

  if [ ! -f .env ]; then cp .env.example .env; ok ".env oluşturuldu (.env.example'dan)"; else warn ".env zaten var, korunuyor"; fi

  local profiles="--profile core"
  if [ "$mode" = "full" ]; then
    profiles="--profile core --profile ai --profile memory --profile observability"
    # Feature flag'leri aç
    set_env LLM_AVAILABLE true
    set_env MEMORY_AVAILABLE true
    set_env OBSERVABILITY_AVAILABLE true
  else
    set_env LLM_AVAILABLE false
    set_env MEMORY_AVAILABLE false
    set_env OBSERVABILITY_AVAILABLE false
  fi

  log "Servisler başlatılıyor ($mode)..."
  $COMPOSE $profiles up -d --build

  log "control-plane sağlıklı olana kadar bekleniyor..."
  bash scripts/wait-for.sh control-plane

  log "Veritabanı migration'ları uygulanıyor..."
  $COMPOSE exec -T control-plane alembic upgrade head

  log "NATS JetStream stream'leri oluşturuluyor..."
  bash scripts/init-nats.sh

  if [ "$mode" = "full" ]; then
    log "Qdrant collection oluşturuluyor..."
    bash scripts/init-qdrant.sh
  fi

  log "Registry ve örnek veri seed'leniyor..."
  $COMPOSE exec -T control-plane python -m app.seed

  print_urls "$mode"
  ok "Kurulum tamam."
}

set_env() { # set_env KEY VALUE  (.env içinde)
  local key="$1" val="$2"
  if grep -qE "^${key}=" .env; then
    sed -i.bak -E "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
  else
    echo "${key}=${val}" >> .env
  fi
}

print_urls() {
  echo ""
  ok "Erişim adresleri:"
  echo "  • Web (Next.js)        http://localhost:${WEB_PORT:-3000}"
  echo "  • Control-plane (API)  http://localhost:${CONTROL_PLANE_PORT:-8000}  (/health, /agents, /docs)"
  if [ "${1:-core}" = "full" ]; then
    echo "  • LiteLLM              http://localhost:${LITELLM_PORT:-4000}"
    echo "  • Qdrant               http://localhost:${QDRANT_PORT:-6333}/dashboard"
    echo "  • Langfuse             http://localhost:${LANGFUSE_PORT:-3001}"
  fi
}

cmd="${1:-setup}"; shift || true
case "$cmd" in
  doctor) doctor ;;
  setup)  setup "${1:-core}" ;;
  *) die "Bilinmeyen komut: $cmd (doctor|setup)" ;;
esac
