#!/usr/bin/env bash
# ACP'ye uygun JetStream stream'lerini oluşturur (idempotent).
# Stream isimleri ACP.md Bölüm 6 ile sabittir — sonradan değiştirmek pahalıdır.
set -euo pipefail

NETWORK="agentic-net"
NATS_SERVER="${NATS_URL:-nats://nats:4222}"
NATS_BOX="natsio/nats-box:0.14.5"

# subject prefix → stream adı
declare -a STREAMS=(
  "ACP_TASK_CREATED:ACP.TASK.CREATED"
  "ACP_TASK_COMPLETED:ACP.TASK.COMPLETED"
  "ACP_TASK_FAILED:ACP.TASK.FAILED"
  "ACP_HANDOFF_REQUESTED:ACP.HANDOFF.REQUESTED"
  "ACP_AGENT_HEARTBEAT:ACP.AGENT.HEARTBEAT"
  "ACP_SYSTEM_EVENT:ACP.SYSTEM.EVENT"
)

run_nats() { docker run --rm --network "$NETWORK" "$NATS_BOX" nats -s "$NATS_SERVER" "$@"; }

for entry in "${STREAMS[@]}"; do
  name="${entry%%:*}"; subject="${entry##*:}"
  if run_nats stream info "$name" >/dev/null 2>&1; then
    echo "• $name zaten var"
  else
    run_nats stream add "$name" \
      --subjects "$subject" \
      --storage file --retention limits --discard old \
      --max-msgs=-1 --max-bytes=-1 --max-age=24h \
      --dupe-window=2m --replicas 1 --defaults >/dev/null
    echo "✓ $name oluşturuldu ($subject)"
  fi
done

echo "✓ JetStream stream'leri hazır."
