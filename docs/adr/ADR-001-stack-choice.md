# ADR-001 — Teknoloji Yığını Seçimi

- **Durum:** Kabul edildi
- **Tarih:** 2026-06-18
- **İlgili:** `STACK.md`

## Bağlam
Dağıtık, sağlayıcı-bağımsız, self-hostable ve tam gözlemlenebilir bir multi-agent platform hedefleniyor (bkz. `ARCHITECTURE.md`, `ACP.md`). Vercel-merkezli "hızlı ship" yaklaşımı (AI SDK + Workflow + Queues) değerlendirildi ama lock-in ve dağıtık hedefe uyumsuzluk nedeniyle reddedildi.

## Karar
Polyglot, vendor-neutral stack:
- **Frontend:** Next.js
- **Control Plane:** FastAPI
- **Agent Runtime:** LangGraph (`AsyncPostgresSaver` ile durable)
- **Messaging:** NATS JetStream
- **İlişkisel:** PostgreSQL · **Cache:** Redis · **Semantik hafıza:** Qdrant
- **LLM:** LiteLLM (çoklu sağlayıcı + fallback + bütçe)
- **Observability:** OpenTelemetry + Langfuse

## Sonuçlar
- (+) Taşınabilir, ölçeklenebilir, sağlayıcıya bağlı değil.
- (+) Durable execution LangGraph + Postgres ile hazır gelir (Temporal'a gerek yok).
- (−) ~7-8 servis → daha fazla operasyon yükü. Compose profilleri (core/ai/memory/observability) ile hafifletildi.
