# Agentic Takım

`atoms.dev` mantığıyla çalışan, her biri kendine has kişiliği ve skill seti olan bir **AI ajan takımı** ve onu çalıştıran **dağıtık runtime** için şablon repo. Klonla → `make setup` → tüm stack local'de ayağa kalkar.

> **Durum:** İskelet (scaffold). Çekirdek bootstrap + minimal çalışan stub'lar hazır; ajan/skill mantığı spesifikasyonlarda tanımlı, kademeli olarak kodlanacak.

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
- [ ] Kaptan: intent parsing + task decomposition (DAG, çok adımlı)
- [ ] Skill execution layer + Skill Contract zorlama
- [ ] Gözcü: kalite skorlama + öğrenme döngüsü
- [ ] Qdrant semantik hafıza entegrasyonu (RAG recall)
- [ ] Web: sohbet + canlı trace görüntüleyici

---

> Detaylı kararların gerekçeleri için [`docs/adr/`](./docs/adr/) klasörüne bakın.
