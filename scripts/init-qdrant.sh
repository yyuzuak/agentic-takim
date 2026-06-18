#!/usr/bin/env bash
# Qdrant collection oluşturur (memory profili, idempotent).
set -euo pipefail

QDRANT="${QDRANT_LOCAL_URL:-http://localhost:6333}"
COLLECTION="${QDRANT_COLLECTION:-agent_memory}"
# OpenAI text-embedding-3-small = 1536 boyut (varsayılan); seed ile uyumlu.
DIM="${QDRANT_VECTOR_SIZE:-1536}"

code="$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT/collections/$COLLECTION")"
if [ "$code" = "200" ]; then
  echo "• '$COLLECTION' collection zaten var"
  exit 0
fi

curl -s -X PUT "$QDRANT/collections/$COLLECTION" \
  -H 'Content-Type: application/json' \
  -d "{\"vectors\": {\"size\": $DIM, \"distance\": \"Cosine\"}}" >/dev/null

echo "✓ '$COLLECTION' collection oluşturuldu (dim=$DIM, cosine)"
