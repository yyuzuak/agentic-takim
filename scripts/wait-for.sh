#!/usr/bin/env bash
# Bir compose servisi 'healthy' olana kadar bekler.
# Kullanım: scripts/wait-for.sh <service> [timeout_sn]
set -euo pipefail

# Göreli yol kullanıyoruz: repo yolunda boşluk olsa bile (ör. "/ - Business/")
# tırnaksız değişken genişlemesi argümanlara bölünmesin diye cd ediyoruz.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SERVICE="${1:?servis adı gerekli}"
TIMEOUT="${2:-120}"
elapsed=0

cid="$(docker compose -f infra/compose/docker-compose.yml --env-file .env ps -q "$SERVICE")"
[ -n "$cid" ] || { echo "✗ $SERVICE container'ı bulunamadı"; exit 1; }

printf "  %s bekleniyor" "$SERVICE"
while true; do
  status="$(docker inspect -f '{{ if .State.Health }}{{ .State.Health.Status }}{{ else }}{{ .State.Status }}{{ end }}' "$cid" 2>/dev/null || echo unknown)"
  case "$status" in
    healthy|running) printf " → %s\n" "$status"; exit 0 ;;
    exited|dead) printf " → %s\n" "$status"; echo "✗ $SERVICE çöktü"; exit 1 ;;
  esac
  [ "$elapsed" -ge "$TIMEOUT" ] && { echo " → zaman aşımı ($status)"; exit 1; }
  sleep 3; elapsed=$((elapsed+3)); printf "."
done
