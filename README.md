# Agentic Takım

`atoms.dev` mantığıyla çalışan, her biri kendine has kişiliği ve skill seti olan bir **AI ajan takımı** ve onu çalıştıran **dağıtık runtime** için şablon repo. Klonla → `make setup` → tüm stack local'de ayağa kalkar.

> **Durum:** v1.3.1 Premium UI tamamlandı. Agent Studio yeniden tasarlandı: sol sidebar, dark/light tema switcher (next-themes), Inter font, CVA tabanlı design system (Button/Card/Badge/Table), framer-motion mikro-animasyon, Recharts veri görselleştirme (Observer). Tüm renkler tema-duyarlı semantic token. (Backend: v1.3 Observer & Metrics — 9 KPI + skor + clustering + advisory.)

## Quickstart (2 dakika)

```bash
git clone <repo> && cd agentic-takim
make setup            # .env'i otomatik oluşturur, core stack'i kurar
```
Ardından:
- http://localhost:3000 — Web
- http://localhost:8000/health — Control-plane (`{"status":"ok"}`)
- http://localhost:8000/agents — 8 ajanlık registry

> `.env`'i elle de hazırlayabilirsiniz: `cp .env.example .env` (opsiyonel; `make setup` zaten yapar).
> Tüm gözlemlenebilirlik + LLM + hafıza için: `make setup-full`.

---

## İçindekiler
- [Architecture Overview](#architecture-overview)
- [Agent Registry](#agent-registry)
- [ACP Message Flow](#acp-message-flow)
- [Local Development](#local-development)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

---

## Architecture Overview

Spesifikasyonlar (tek doğruluk kaynağı):
| Belge | İçerik |
|------|--------|
| [CLAUDE.md](./CLAUDE.md) | Ajan personaları, skill'ler, kurallar, standartlar |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Runtime: DAG yürütme, validation, execution modları |
| [ACP.md](./ACP.md) | Ajanlar-arası iletişim protokolü |
| [STACK.md](./STACK.md) | Teknoloji yığını kararı |
| [docs/adr/](./docs/adr/) | Mimari karar kayıtları (ADR) |

**Stack:** Next.js · FastAPI · LangGraph · NATS JetStream · PostgreSQL · Redis · Qdrant · LiteLLM · OpenTelemetry + Langfuse.

### Mimari Kuralı (guardrail)
```
Web (Next.js) → Control-plane (FastAPI) → NATS (JetStream) → Agents (LangGraph)
```
- **Next.js API routes KULLANILMAZ.** Tüm backend mantığı control-plane'dedir (tek backend).
- Ajanlar birbirini doğrudan çağırmaz; yalnızca Kaptan/bus üzerinden (bkz. [ADR-002](./docs/adr/ADR-002-acp-design.md)).

### Servisler
| Dizin | Rol |
|------|-----|
| `apps/web` | Next.js arayüzü |
| `services/control-plane` | FastAPI — routing/orkestrasyon API (Kaptan) |
| `services/agent-runner` | LangGraph graph yürütme (durable, AsyncPostgresSaver) |
| `services/worker` | Arka plan/tool/embedding işleri (NATS tüketici) |
| `services/tool-runtime` | Tool adapter runtime (port 8001) — dış sistem çağrıları, circuit breaker, compensation |
| `services/observer` | Observer (port 8002) — read-only sidecar analytics: KPI/score/cluster/recommendation |
| `packages/schemas` | Paylaşılan sözleşmeler (ACP, Skill Contract, Registry, Events) — sistemin kalbi |

---

## Agent Registry

Ajan → skill eşlemesi tek kaynaktan: [`config/agents.json`](./config/agents.json). `make seed` bunu `agents`, `skills`, `agent_skills` tablolarına yükler; çalışma-zamanı registry buradan okunur (ileride UI'dan düzenlenebilir).

| Ajan | Rol |
|------|-----|
| 🧭 Kaptan | Takım Lideri (Orchestrator) |
| 📋 Pusula | Ürün Yöneticisi |
| 🏛️ Mimar | Sistem Mimarı |
| 💻 Usta | Yazılım Mühendisi |
| 📊 Veda | Veri Bilimci |
| 🔍 Dedektif | Derin Araştırmacı |
| 🚀 Zirve | SEO Uzmanı |
| 🧠 Gözcü | Observer (meta-ajan) |

Çalışan registry'yi görmek için: `curl http://localhost:8000/agents`.

---

## ACP Message Flow

Ajanlar event-driven, sözleşme-öncelikli ACP ile haberleşir (bkz. [ACP.md](./ACP.md)). Kanonik JetStream subject'leri (`init-nats.sh` oluşturur, `events.v1` ile sabit):

```
ACP.TASK.CREATED      ACP.TASK.COMPLETED    ACP.TASK.FAILED
ACP.HANDOFF.REQUESTED ACP.AGENT.HEARTBEAT   ACP.SYSTEM.EVENT
```

Örnek akış (`trace_id` tüm zinciri birbirine bağlar):
```
Kaptan → Dedektif → Pusula → Mimar → Usta → Kaptan (birleştirme)
        ⟂ Gözcü tüm adımları salt-okunur izler.
```

### Çalışan task akışı (uçtan uca)
```bash
# Görev gönder — Kaptan skill'i ilgili ajana route eder, NATS'a yayınlar
curl -X POST localhost:8000/tasks -H 'Content-Type: application/json' \
  -d '{"goal":"Bir REST API tasarla","skill":"api-sozlesme-tasarimci"}'
# → {"task_id":"...","agent":"mimar","status":"running"}

# Sonucu sorgula (agent-runner işleyip ACP.TASK.COMPLETED'a yazınca 'done')
curl localhost:8000/tasks/<task_id>
# → {"status":"done","result":{"steps":["plan: ...","execute: ..."]}}
```
Akış: `POST /tasks` → control-plane (Kaptan routing) → `ACP.TASK.CREATED` → agent-runner (LangGraph, durable) → `ACP.TASK.COMPLETED` → control-plane sonucu DB'ye yazar. Skill bilinmiyorsa fallback Kaptan'dır.

### Çok-adımlı DAG (skill vermeden)
`skill` belirtmezseniz Kaptan hedefi bir **DAG**'a böler ve düğümleri bağımlılık sırasıyla farklı ajanlara dağıtır:
```bash
curl -X POST localhost:8000/tasks -H 'Content-Type: application/json' \
  -d '{"goal":"Bir SaaS ürünü tasarla ve backend kodla"}'
# plan: t1 dedektif + t2 veda (paralel) → t3 pusula (join) → t4 mimar → t5 usta
curl localhost:8000/tasks/<id>   # nodes[] her düğümün durumu + result; tamamlanınca aggregate
```
`type: "research"` veya hedefte "araştır/analiz" geçmesi araştırma şablonunu seçer.

**Plan üretimi (LLM vs kural):** `ai` profili açık ve geçerli bir API key varsa (`.env`'e `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` ekleyip `make setup-full`), Kaptan DAG'ı **LLM** ile üretir (`planner: "llm"`). LLM yoksa/başarısızsa/şema dışıysa kural tabanlı şablona düşer (`planner: "rule"`, `planner_error` ile neden). LLM **yalnızca plan üreticisidir**; düğümleri yine agent-runner çalıştırır. POST `/tasks` yanıtı `planner` + `planner_error` alanlarını döner.

---

## Local Development

### Ön-koşullar
- **Docker** + Docker Compose (zorunlu)
- Node 20, Python 3.12, pnpm 9, uv (yerel geliştirme için; sürümler `.tool-versions`)
- Alternatif: VS Code + **Dev Containers** → `.devcontainer` her şeyi otomatik kurar.

### Kurulum
```bash
make doctor        # ön-koşulları kontrol et
make setup         # CORE profili: postgres, redis, nats, control-plane, agent-runner, worker, web
# veya
make setup-full    # + ai (LiteLLM) + memory (Qdrant) + observability (OTel, Langfuse)
```

Kurulum sonrası:
- Web → http://localhost:3000
- Control-plane → http://localhost:8000 (`/health`, `/agents`, `/docs`)
- (full) LiteLLM :4000 · Qdrant :6333 · Langfuse :3001

### Profiller
| Profil | Servisler | Komut |
|--------|-----------|-------|
| `core` | postgres, redis, nats, control-plane, agent-runner, worker, web | `make setup` |
| `ai` | litellm | (full'e dahil) |
| `memory` | qdrant | (full'e dahil) |
| `observability` | otel-collector, langfuse | (full'e dahil) |

API key olmadan `make setup` çalışır: `LLM_AVAILABLE=false` ile graceful degradation. Key'leri `.env`'e girip `make setup-full` ile LLM'i etkinleştir.

### Komutlar
```bash
make up / down / reset / logs S=control-plane
make migrate     # alembic upgrade head
make seed        # registry + örnek veri
make validate    # şema + registry doğrulama (CI ile aynı)
make test        # pytest
```

### Durable execution kanıtı (kill → resume)
`agent-runner`, LangGraph + `AsyncPostgresSaver` ile çalışır; yürütme süreçler arası dayanıklıdır:
```bash
C="docker compose -f infra/compose/docker-compose.yml --env-file .env"
$C exec agent-runner python -m runner.resume_demo start demo-1   # execute öncesi durur, checkpoint Postgres'e
$C kill agent-runner && make up                                  # süreci öldür, yeniden başlat
$C exec agent-runner python -m runner.resume_demo resume demo-1  # kalıcı durumdan tamamlar
```
Beklenen: `resume` çıktısı `steps=['plan: ...','execute: ...']`, `next=()` — yani iş, çökme sonrası kaldığı yerden bitti.

### Human-in-the-Loop (onaylı yürütme)
`require_approval: true` ile gönderilen görev önce **onay bekler** (`awaiting_approval`); yürütme onaydan sonra başlar. Onay durumu Postgres'te kalıcıdır — control-plane çökse bile görev beklemede kalır.
```bash
# 1) Onay gerektiren görev → plan üretilir ama çalışmaz
curl -X POST localhost:8000/tasks -H 'Content-Type: application/json' \
  -d '{"goal":"CRM sistemi kur","require_approval":true,"actor":"yasin"}'
# → {"status":"awaiting_approval","version":1,"plan":[...]}

curl localhost:8000/tasks/<id>/plan       # planı incele
curl localhost:8000/tasks/<id>/approval   # onay durumu (kim/sürüm/zaman)

# 2a) Düzenle (yeni sürüm) — sadece awaiting_approval'da
curl -X POST localhost:8000/tasks/<id>/edit -H 'Content-Type: application/json' \
  -d '{"actor":"yasin","nodes":[{"key":"t1","skill":"prd-uretici","depends_on":[]}]}'
# 2b) Reddet → cancelled
curl -X POST localhost:8000/tasks/<id>/reject -d '{"actor":"yasin","reason":"kapsam dışı"}'
# 2c) Onayla → running → done
curl -X POST localhost:8000/tasks/<id>/approve -d '{"actor":"yasin"}'
```
Edit her seferinde plan'ın **değişmez bir sürümünü** (`task_plan_versions`) saklar (audit zemini). `actor` alanı RBAC/audit için taşınır.

### Retry & Failure (v0.6)
Düğüm hataları sınıflandırılır (ACP `ErrorCode`) ve retry politikasına göre yeniden denenir. **Postgres = source of truth, NATS = signal.**
```bash
# Fault injection ile retry → başarı (ilk 2 deneme fail, sonra success)
curl -X POST localhost:8000/tasks -H 'Content-Type: application/json' \
  -d '{"goal":"X","skill":"prd-uretici","inputs":{"fail_times":2},"max_retries":3}'
# node: retry_count=2 → done; workflow done

# Tükenme → DLQ
curl -X POST localhost:8000/tasks -d '{"goal":"X","skill":"prd-uretici","inputs":{"fail_times":99},"max_retries":2}'
curl localhost:8000/tasks/<id>/dlq                       # dead_letter_nodes (retry_history dahil)
curl -X POST localhost:8000/dlq/<node_id>/replay -d '{"actor":"yasin"}'   # replay → DAG devam eder
```
- **Retryable:** TRANSIENT, TIMEOUT, UNKNOWN · **Non-retryable:** SCHEMA, PERMISSION, LOGICAL, BUDGET (anında DLQ).
- **Policy:** `immediate | exponential` (varsayılan, +jitter) `| manual` (ilk hatada DLQ → `POST /tasks/{id}/nodes/{key}/retry`).
- **Scheduler:** Postgres `retry_at` + `FOR UPDATE SKIP LOCKED` (async-sleep değil, dağıtık-güvenli).
- **Exactly-once:** `exec_id = sha256(task:node:attempt)` + `processed_executions` → çift teslimat yok sayılır.
- **DAG-safe:** retry'daki düğümün child'ı asla çalışmaz; bağımsız düğümler devam eder.

---

## Troubleshooting

| Belirti | Çözüm |
|--------|-------|
| `make setup` ön-koşulda duruyor | `make doctor` çıktısına bak; Docker çalışıyor mu? |
| control-plane `unhealthy` | `make logs S=control-plane`; Postgres healthy mi (`make logs S=postgres`)? |
| Port çakışması (3000/8000/...) | `.env` içindeki `*_PORT` değişkenlerini değiştir. |
| `/agents` boş | `make seed` çalıştır; migration uygulandı mı (`make migrate`)? |
| NATS stream yok | `make init-nats`; `agentic-net` ağı ayakta mı? |
| Qdrant bağlanmıyor | Sadece `memory` profilinde var; `make setup-full` kullan. |
| Sıfırdan başla | `make reset && make setup` |

---

## Roadmap

- [x] Spesifikasyonlar (CLAUDE / ARCHITECTURE / ACP / STACK) + ADR'ler
- [x] Self-bootstrapping iskelet (compose profilleri, tek komut kurulum, minimal stub'lar)
- [x] ACP mesaj akışının uçtan uca implementasyonu (control-plane → NATS → agent-runner → result)
- [x] Kaptan: skill→agent routing (registry tabanlı, fallback Kaptan)
- [x] Kaptan: intent parsing + task decomposition (çok-adımlı DAG; paralel + join + bağımlılık)
- [x] LLM tabanlı intent parsing + decomposition (LiteLLM) — **LLM yalnızca plan üretici**;
      guardrail (skill whitelist, asiklik, ≤8 düğüm) + retry; başarısızsa kural tabanlı fallback
- [x] **Human-in-the-Loop** — DAG preview → approve/edit/reject → execute; plan versioning,
      actor metadata, durable `awaiting_approval` (Postgres; restart sonrası approve çalışır)
- [x] v0.5.1 Audit Trail — event-sourced context (v0.7) ile karşılandı; her düğüm geçişi, artifact ve critique olayı append-only `task_context_events`'e yazılır
- [x] **v0.6 Retry + Failure Semantics** — node fault model (retry_count/max_retries/policy),
      failure taxonomy (ACP ErrorCode), Postgres retry scheduler (exponential+jitter, SKIP LOCKED),
      fingerprint dedup (exactly-once final state), DLQ (Postgres+NATS) + replay
- [x] **v0.7 Multi-Agent Collaboration** — event-sourced context (append-only events + deterministic
      reducer → snapshot, single-writer), producer/critic/synthesizer rolleri, artifact+critique
      projeksiyonları; critic producer'ı değiştirmez (provenance korunur)
- [x] **v0.8 Memory-Aware Planning** — geçmiş başarılı görevlerden recall (Qdrant), planner
      enrichment (LLM few-shot / rule template bias); guardrail'ler: MIN_SCORE, diversity,
      confidence+drift, copy-risk telemetry, idempotent two-phase store, retrieval feedback
- [x] **v0.9 Tool Execution Framework** — ayrı Tool Runtime katmanı (ACP.TOOL.REQUEST/RESULT);
      node kinds reasoning|tool|approval; idempotent (at-most-once) + permission + audit (tool_invocations);
      simulated tools (check_stock/create_quote/generate_pdf/send_whatsapp); v0.6 retry/DLQ yeniden kullanımı
- [x] **v0.9.1 Tool Safety Layer** — dry-run modu, runtime+plan-time argüman şema doğrulaması, Redis sliding-window rate-limit (RATE_LIMIT→retry), atomic compensation ledger (tool_compensations), tool_invocations audit genişletme
- [x] **v1.0 Agentic OS MVP** — Next.js web UI: görev oluştur, canlı DAG görselleştirme (node onay butonu dahil), tool invocation viewer, compensation ledger, audit timeline (event stream), hafıza tarayıcı + recall; GET /tasks list endpoint
- [x] **v1.1 Production Connectors** — ToolAdapter Protocol (Protocol + runtime_checkable), ERPAdapter (BizimHesap/Logo/Netsis/Mikro enum, dry_run), WhatsAppAdapter (graph.facebook.com), Circuit Breaker (Redis-persisted CLOSED→OPEN→HALF_OPEN), tool-runtime HTTP API (port 8001), compensation apply endpoint; secrets katmanı (tek os.environ erişim noktası)
- [x] **v1.2 Agent Studio** — Tailwind + shadcn/ui + React Flow DAG (otomatik topolojik layout, inline Onayla butonu, animasyonlu kenarlar) + TanStack Query polling; 5 ekran: Studio (goal input + 3-kolon grid), Görevler, Task Detail (DAG|Timeline split), Tool Center (adapter health + capabilities tablosu), Hafıza Explorer, Observer stub
- [x] **v1.3 Observer & Metrics** — bağımsız `services/observer` (port 8002, read-only sidecar analytics plane); 9 KPI (workflow/planner/retry/dlq/tool/memory/compensation) mevcut tablolardan windowed (1h/24h/7d) hesaplama, MIN_SAMPLES cold-start fallback; weighted composite skor (Bayesian tool smoothing, nonlinear retry_health), noise-guarded anomaly delta; rule-based failure clustering (cluster_strength + severity escalation); advisory recommendations (linked_kpis); in-process cache (30s TTL); service-to-service auth (X-Internal-Token); bounded query invariant (enforced LIMIT, no full scan); canlı Observer Dashboard (6 bölüm)
- [x] **v1.3.1 Premium UI** — Agent Studio yeniden tasarımı: sol sidebar nav, dark/light tema switcher (next-themes, CSS-var iki palet), Inter (next/font), CVA design system (Button/Card/Badge/Table/Skeleton), framer-motion (stagger kartlar + mobil drawer), Recharts (Observer tool-reliability bar + 3-window skor trendi); tüm renkler tema-duyarlı semantic token (hardcoded dark-only renk = 0)
- [ ] v0.8.1 Memory Consolidation (dedup/decay/scoring/forgetting)
- [ ] v1.4 Observer Advise — recommendation → planner prompt injection; statistical confidence layer, retry causality, cross-cluster correlation, HMAC/rotating service auth
- [ ] v2.0 SaaS Multi-Tenant (organizations, users, roles, billing, API keys)

---

> Detaylı kararların gerekçeleri için [`docs/adr/`](./docs/adr/) klasörüne bakın.
