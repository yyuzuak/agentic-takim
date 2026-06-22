# STACK.md — Teknoloji Yığını Kararı

> ℹ️ **KAPSAM NOTU:** Bu bir **teknoloji kararı belgesidir.** Spesifikasyonların (`CLAUDE.md`, `ARCHITECTURE.md`, `ACP.md`) **hangi teknolojilerle** hayata geçtiğini sabitler. Burada belgelenen stack artık **implemente edilmiştir ve çalışmaktadır** (`make setup` ile ayağa kalkar); tamamlanmış işler için bkz. `README.md` → Roadmap.

---

## 1. Seçilen Stack (Özet)

| Katman | Teknoloji |
|--------|-----------|
| Frontend | **Next.js** |
| Control Plane (API) | **FastAPI** |
| Agent Runtime | **LangGraph** |
| Messaging / Event Bus | **NATS (JetStream)** |
| İlişkisel Depolama | **PostgreSQL** |
| Cache / Ephemeral | **Redis** |
| Semantik Hafıza | **Qdrant** |
| LLM Katmanı | **LiteLLM** |
| Observability | **OpenTelemetry** + **Langfuse** |
| Şema / Sözleşme | **Pydantic** → OpenAPI → **Zod** |
| Paketleme | **Docker Compose** (dev) / **Kubernetes** (prod) |

---

## 2. Spec ↔ Teknoloji Eşleme Tablosu

Her teknoloji, hangi spesifikasyon bileşenini hayata geçirdiğiyle birlikte:

| Spec bileşeni (kaynak) | Teknoloji | Not |
|---|---|---|
| DAG yürütme + checkpoint + dinamik replan + Loop Mode + human-in-the-loop (`ARCHITECTURE.md` 3, 10, 13.1–13.3, 13.10) | **LangGraph** | Stateful graph + `interrupt` (HITL) + cycle desteği. **Postgres checkpointer** ile durable. Ayrı Temporal/Workflow gereksiz. |
| Event Bus + topic'ler + DLQ + at-least-once (`ACP.md` 6, 8) | **NATS JetStream** | Düz NATS değil — JetStream persistence/replay/DLQ verir. |
| Proje Hafızası: yapısal state, trace, ADR, görev durumu (`CLAUDE.md` 8; `ACP.md` 3) | **PostgreSQL** | Aynı zamanda LangGraph checkpointer backend'i. |
| Ephemeral state, idempotency key, dedup (`ACP.md` 7.3, 9) | **Redis** | TTL'li hızlı key-value; heartbeat/lock. |
| Semantik / uzun-dönem hafıza, RAG recall, embeddings (`CLAUDE.md` 8; Veda `nlp-isleme-motoru`, Dedektif recall) | **Qdrant** | Vektör DB; Postgres'in anlamsal tamamlayıcısı (bkz. Bölüm 5). |
| Çoklu sağlayıcı + fallback + **Bütçe Yöneticisi** (`ARCHITECTURE.md` 13.5) | **LiteLLM** | Proxy: unified API + fallback + budget/rate-limit/cost yerleşik. |
| Routing, orkestrasyon API'si, ajan tetikleme | **FastAPI** | Kaptan'ın control plane'i; OpenAPI üretir. |
| Kullanıcı arayüzü, sohbet, dashboard | **Next.js** | OpenAPI'den üretilen tiplerle FastAPI'ye bağlanır. |
| İz/span'ler, kalite ve maliyet gözlemi (`ARCHITECTURE.md` Gözcü; 13.7) | **OpenTelemetry** + **Langfuse** | OTel = altyapı span'leri (vendor-neutral); Langfuse = LLM prompt/token/eval izleri (açık kaynak, OTel uyumlu). |
| Skill Contract + Schema Registry + envelope doğrulama (`CLAUDE.md` 6; `ACP.md` 1, 11) | **Pydantic** → OpenAPI → **Zod** | Tek doğruluk kaynağı: Pydantic'te tanımla, OpenAPI'ye yay, Next.js'te Zod tipi üret. |

---

## 3. Rötuşlar (gerekçeli)

Senin önerine yapılan dört bilinçli değişiklik:

1. **NATS → NATS JetStream.** Düz NATS fire-and-forget'tir; ACP'nin at-least-once + DLQ + replay gereksinimleri (Bölüm 6-8) JetStream gerektirir.
2. **AI Gateway → LiteLLM.** Stack'in geri kalanı self-hosted/vendor-neutral olduğu için tutarlılık; ayrıca LiteLLM'in yerleşik budget/rate-limit/cost yönetimi **Bütçe Yöneticisi'ni** (13.5) bedavaya getirir.
3. **OTel + Langfuse.** OTel tek başına altyapı izini verir; LLM'e özel iz (prompt, token, eval, kalite skoru) için Langfuse eklenir — Gözcü'nün gözlem ihtiyacını besler.
4. **Pydantic → OpenAPI → Zod zinciri.** İki dilli (Python + TS) bir sistemde şema sürüklenmesini (drift) önlemek için şemalar Python'da Pydantic ile tanımlanır, FastAPI OpenAPI'sine yayılır, Next.js'te Zod/TS tipine dönüştürülür.

---

## 4. İki Katmanlı Hafıza

Proje Hafızası (`CLAUDE.md` Bölüm 8) iki teknolojiye bölünür:

- **PostgreSQL — yapısal hafıza:** aktif PRD, mimari kararlar (ADR), görev DAG durumu, ortak sözlük, kalite skorları, trace kayıtları. Sorgulanabilir, tutarlı, ilişkisel.
- **Qdrant — anlamsal hafıza:** embeddings, geçmiş araştırma/çıktı recall'ı, benzerlik araması (RAG). "Bunu daha önce nerede gördük?" sorusunun cevabı.

> Ajan, sıkıştırılmış bağlamı (`ACP.md` 5) yetersiz bulursa önce Postgres'ten yapısal genişletme, gerekirse Qdrant'tan semantik recall ister.

---

## 5. Operasyon (Dürüst Not)

Bu mimari **~7-8 ayrı servis** demek: FastAPI, LangGraph worker'ları, NATS, Postgres, Redis, Qdrant, LiteLLM, Langfuse.

- **Dev:** `docker-compose` ile hepsi tek komutla ayağa.
- **Prod:** **Kubernetes** (servis başına ölçekleme, ajan worker'ları için yatay ölçek).
- **Takas:** Vercel-merkezli rotaya göre belirgin şekilde **daha fazla operasyon yükü** — ama karşılığında gerçek, taşınabilir, dağıtık (multi-node) bir ajan platformu. Specs'in iddiası (distributed agents) bunu gerektiriyor; bilinçli kabul edilen takas.

---

## 6. Repo Yapısı (kuruldu)

```
agentic-takim/
├── CLAUDE.md ARCHITECTURE.md ACP.md STACK.md   # spec'ler (kökte)
├── README.md Makefile .env.example .tool-versions
├── .devcontainer/  .github/workflows/ci.yml
├── apps/web/                 # Next.js — Agent Studio UI (DAG/timeline/tool/memory/observer)
├── services/
│   ├── control-plane/       # FastAPI — routing/orkestrasyon API + Alembic
│   ├── agent-runner/        # LangGraph graph yürütme (AsyncPostgresSaver)
│   ├── worker/              # NATS tüketici (sistem olayları / audit; genişletilebilir)
│   ├── tool-runtime/        # Tool adapter runtime (8001) — dış çağrılar, circuit breaker, compensation
│   ├── observer/            # Observer (8002) — read-only analytics: KPI/score/cluster/recommendation
│   ├── builder/             # Builder (8003) — artifact → doğrulanmış repo (assemble+validate+persist)
│   ├── sandbox/             # Sandbox (8004) — build execution (npm install/prisma/build, stateless)
│   └── preview/             # Preview (8005, app 8100) — canlı npm run dev, tek-slot, TTL auto-stop
├── packages/
│   ├── schemas/             # Pydantic: acp/v1, skill-contract/v1, agent-registry/v1, events/v1
│   ├── sdk/                 # üretilen istemci (placeholder)
│   └── shared/              # ortak util (placeholder)
├── config/agents.json       # ajan→skill registry (seed kaynağı)
├── infra/
│   ├── compose/             # docker-compose — profiller: core / ai / memory / observability
│   ├── postgres/ litellm/ otel/
│   └── (k8s/ — prod, ileride)
├── scripts/                 # bootstrap, wait-for, init-nats, init-qdrant
└── docs/adr/                # ADR-001..003
```

> **Compose profilleri:** `core` (litellm yok, API key gerekmez) · `ai` (litellm) · `memory` (qdrant) · `observability` (otel+langfuse). `make setup`=core, `make setup-full`=hepsi.

---

## 7. Reddedilen Alternatifler (kısa)

- **Vercel Workflow + Queues:** Hızlı ama lock-in; dağıtık/taşınabilir hedefe ters. (İlk önerimdi, geri çekildi.)
- **Temporal:** Güçlü durable orchestration, ama **LangGraph + Postgres checkpointer + JetStream** ile büyük ölçüde örtüşüyor → bu ölçekte fazlalık.
- **Saf Python orchestration (elle DAG):** LangGraph zaten checkpointing/HITL/cycle verirken tekerleği yeniden icat etmek.

---

> **Durum:** Stack implemente edildi ve çalışıyor. `make setup` ile core stack ayağa kalkar; ACP mesaj akışı, Kaptan orkestrasyonu, tool runtime, observer ve app-builder hattı (builder/sandbox/preview) uçtan uca hayata geçirildi. Tamamlanmış milestone'lar ve sıradaki adım için bkz. README → Roadmap.
