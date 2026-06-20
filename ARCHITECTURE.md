# ARCHITECTURE.md — Agentic Runtime Spesifikasyonu (v1)

> ⚠️ **KAPSAM NOTU — ÖNEMLİ:** Bu belge bir **spesifikasyondur, çalışan kod değildir.** Buradaki tüm kod blokları **sözde-kod (pseudo-code)** veya **örnek şemadır**; gerçekte çalışan bir orchestrator, DAG yürütücü veya mesaj kuyruğu **yoktur**. Şu an sistem, tek bir modelin `CLAUDE.md`'yi okuyup rolleri canlandırması (roleplay) ile çalışır. Bu belge, ileride **gerçek runtime'a** dönüştürülecek tasarımı tanımlar. Somut teknoloji seçimleri için bkz. **`STACK.md`** (Next.js, FastAPI, LangGraph, NATS JetStream, Postgres, Redis, Qdrant, LiteLLM, OpenTelemetry).
>
> Ajan personaları, skill listeleri ve çalışma kuralları için bkz. **`CLAUDE.md`**. Bu belge "nasıl çalışacağı" (runtime); CLAUDE.md "kim oldukları" (persona+kural).

---

## 1. Sistem Genel Bakış

Sistem yönlü, döngüsüz bir **yürütme grafiği (Directed Acyclic Execution Graph — DAG)** üzerinde çalışır.

```
USER INPUT
   │
   ▼
[ORCHESTRATOR / KAPTAN]
   │  ├── niyet ayrıştırma (intent parsing)
   │  ├── görev parçalama (task decomposition → DAG)
   │  └── ajan yönlendirme (agent routing)
   ▼
[AGENT EXECUTION LAYER]
   │  ├── Pusula    (Ürün)
   │  ├── Dedektif  (Araştırma)
   │  ├── Mimar     (Mimari)
   │  ├── Usta      (Mühendislik)
   │  ├── Veda      (Veri/AI)
   │  └── Zirve     (SEO)
   ▼
[RESULT AGGREGATOR]
   │  ├── doğrulama (validation)
   │  ├── çakışma çözümü (conflict resolution)
   │  └── biçimlendirme (formatting)
   ▼
FINAL OUTPUT

         ⟂ Kesişen (cross-cutting): GÖZCÜ (Observer) tüm katmanları izler.
```

---

## 2. Core Runtime Spec (Engine Seviyesi)

### 2.1 Message Envelope (Devir Zarfı — KRİTİK)

Her ajan **yalnızca** bu zarfı görür (izolasyon). CLAUDE.md Bölüm 7 ile hizalıdır. Mesajlaşma protokolünün tam tanımı (tüm mesaj tipleri, trace, routing, failure model) için bkz. **`ACP.md`**.

```jsonc
// örnek şema — pseudo
{
  "task_id": "uuid",
  "agent": "usta",
  "skill": "frontend-sistem-insaaci",
  "input": {
    "context": "...sıkıştırılmış bağlam (semantic summary)...",
    "goal": "...",
    "constraints": [],
    "artifacts": []
  },
  "expected_output": "schema_ref",   // bkz. Bölüm 13.9 Schema Registry
  "trace": {
    "parent_task": "uuid",
    "depth": 2
  }
}
```

### 2.2 Agent Response Contract

```jsonc
// örnek şema — pseudo
{
  "task_id": "uuid",
  "status": "success | failure | partial",
  "skill_used": "frontend-sistem-insaaci",
  "output": {
    "result": {},
    "artifacts": [],
    "assumptions": [],   // ajanın yaptığı varsayımlar (denetlenebilirlik)
    "risks": []
  },
  "confidence": 0.0,       // ⚠ self-report; bağlayıcı değil — bkz. Bölüm 13.7
  "next_handoff": "mimar | null"
}
```

---

## 3. Orchestrator (Kaptan) — Runtime Mantığı

### 3.1 Pipeline

```python
# pseudo-code
def orchestrate(user_input):
    intent = parse_intent(user_input)
    tasks  = decompose(intent)
    graph  = build_dag(tasks)

    results = {}
    for node in topological_sort(graph):
        if not dependencies_ready(node, results):
            mark(node, "blocked"); continue

        agent     = route_agent(node)
        response  = execute_agent(agent, node)   # retry+idempotency: Bölüm 13.2
        validated = validate(response)           # ağırlıklı skor: Bölüm 8

        if validated.failed:
            graph = replan(graph, node, response) # dinamik replan: Bölüm 13.1
            continue

        results[node.id] = validated
        if conflict_detected(validated):
            resolve_conflict(validated)           # cakisma-cozucu

    return aggregate(results)
```

### 3.2 Intent Parser (Kaptan skill: `niyet-ayristirma`)

```jsonc
// örnek çıktı şeması — pseudo
{
  "goal": "string",
  "type": "build | research | analyze | optimize",
  "complexity": "low | medium | high",
  "required_agents": ["usta", "mimar"],
  "constraints": { "time": null, "budget": null, "tech": [] }
}
```

---

## 4. Task Decomposition Engine (Kaptan skill: `gorev-parcalama-motoru`)

Her istek → DAG node'larına bölünür.

```jsonc
// örnek — pseudo
{
  "nodes": [
    { "id": "t1", "agent": "dedektif", "skill": "pazar-zekasi-motoru",        "depends_on": [] },
    { "id": "t2", "agent": "pusula",   "skill": "prd-uretici",                "depends_on": ["t1"] },
    { "id": "t3", "agent": "mimar",    "skill": "sistem-mimarisi-uretici",    "depends_on": ["t2"] }
  ]
}
```

---

## 5. Agent Registry (Core Runtime Config)

`agents.json` — ajan→skill eşlemesi. CLAUDE.md'deki Türkçe skill id'leriyle birebir tutarlıdır.

```jsonc
// örnek config — pseudo
{
  "kaptan":   { "skills": ["niyet-ayristirma", "gorev-parcalama-motoru", "ajan-yonlendirme-motoru",
                            "baglam-ozetleme", "yurutme-denetcisi", "cakisma-cozucu"] },
  "pusula":   { "skills": ["prd-uretici", "mvp-kapsam-daraltici", "kullanici-yolculugu-simulatoru",
                            "gereksinim-dogrulayici", "onceliklendirme-motoru"] },
  "mimar":    { "skills": ["sistem-mimarisi-uretici", "api-sozlesme-tasarimci", "veri-modelleme-motoru",
                            "teknoloji-secim-motoru", "olceklenebilirlik-simulatoru", "guvenlik-mimarisi-denetcisi"] },
  "usta":     { "skills": ["fullstack-kod-uretici", "frontend-sistem-insaaci", "backend-servis-insaaci",
                            "entegrasyon-motoru", "test-cercevesi-uretici", "hata-ayiklama-motoru"] },
  "veda":     { "skills": ["eda-motoru", "ml-pipeline-tasarimci", "model-degerlendirme-motoru",
                            "nlp-isleme-motoru", "veri-pipeline-insaaci", "web-kazima-orkestratoru"] },
  "dedektif": { "skills": ["derin-web-arastirma", "pazar-zekasi-motoru", "rakip-tersine-muhendislik",
                            "akademik-literatur-tarayici", "kullanici-icgoru-cikarici", "gercek-dogrulama-motoru"] },
  "zirve":    { "skills": ["anahtar-kelime-niyet-kumeleme", "seo-icerik-motoru", "teknik-seo-denetcisi",
                            "buyume-dongusu-tasarimci", "icerik-optimizasyon-motoru", "cok-dilli-seo-motoru"] },
  "gozcu":    { "skills": ["cikti-kalite-skorlama", "anomali-tespiti", "surekli-iyilestirme", "ogrenme-dongusu"],
                "type": "meta" }  // pipeline dışı, kesişen meta-ajan
}
```

---

## 6. Skill Execution Layer

Her skill, bir **function pointer** gibi çözümlenir.

```python
# pseudo-code
SKILL_REGISTRY = {
    "prd-uretici":             prd_uretici,
    "sistem-mimarisi-uretici": sistem_mimarisi_uretici,
    "fullstack-kod-uretici":   fullstack_kod_uretici,
    # ... (Bölüm 5'teki tüm skill'ler)
}
```

Her skill, **Skill Sözleşmesi'ne** (CLAUDE.md Bölüm 6) uymak zorundadır: `ad, girdi-sema, cikti-sema, bagimliliklar, determinizm, token-maliyeti, hata-modlari`.

---

## 7. Routing Engine (En Kritik Parça — Kaptan skill: `ajan-yonlendirme-motoru`)

```python
# pseudo-code
def route_agent(task):
    skill = task.skill
    for agent, config in AGENT_REGISTRY.items():
        if config.get("type") == "meta":      # Gözcü yönlendirilmez
            continue
        if skill in config["skills"]:
            return agent
    return "kaptan"  # fallback
```

> Genişletme: yetenek eşleştirmenin ötesinde **yük dengeleme**, **bağımlılık sırası** ve skill'in `determinizm` alanına göre sıcaklık (temperature) ayarı dikkate alınır.

---

## 8. Validation Layer (Guardrail Sistemi) — DÜZELTİLMİŞ

> ⚠️ Naif sürüm `sum(checks) > 0.8` boolean'ları topluyordu — yanlış. Doğrusu: **ağırlıklı skor + hard/soft gate** ayrımı.

```python
# pseudo-code
HARD_GATES = [schema_validation, dependency_check]   # başarısızsa => REDDET
SOFT_GATES = {                                        # ağırlıklı skor
    hallucination_check: 0.4,
    completeness_check:  0.4,
    consistency_check:   0.2,
}

def validate(response):
    # 1) Hard gate: biri bile düşerse anında reddet
    for gate in HARD_GATES:
        if not gate(response):
            return Result(failed=True, reason=gate.__name__)

    # 2) Soft gate: ağırlıklı skor
    score = sum(weight * check(response) for check, weight in SOFT_GATES.items())
    return Result(failed=(score < 0.8), score=score)
```

---

## 9. Result Aggregator (Final Output Engine)

```python
# pseudo-code
def aggregate(results):
    return {
        "summary":        synthesize(results),       # Kaptan birleştirir
        "artifacts":      merge_artifacts(results),
        "decision_trace": build_trace(results)       # hangi ajan ne yaptı (denetlenebilirlik)
    }
```

---

## 10. Execution Modes (Yürütme Modları)

**MODE 1 — SEQUENTIAL (sıralı)**
```
Dedektif → Pusula → Mimar → Usta
```

**MODE 2 — PARALLEL (optimize)**
```
Dedektif ┐
         ├──> Pusula
Veda     ┘
Mimar + Usta  (paralel build)
```
> Eşzamanlılık kontrolü: `max_parallelism` ve dış API hız limitleri (backpressure) uygulanır.

**MODE 3 — LOOP (iyileştirme döngüsü)**
```
Usta → Kaptan → Mimar → Usta  (refinement loop)
```
> ⚠️ **Sonsuz döngü koruması (zorunlu):** Döngü ancak şu koşullarla durur:
> - `iteration < max_iterations` (ör. 3), **VE**
> - `iyilesme_deltasi >= esik` — iki tur arası kalite skoru artışı eşiğin altına düşerse döngü sonlanır (yakınsama).

---

## 11. Memory & Context System

Bağlam sıkıştırma kuralı (Kaptan skill: `baglam-ozetleme`):

```
ham_baglam  →  anlamsal_ozet (semantic summary)  →  ajana-özel dilim (agent-specific slice)
```

Her ajan **yalnızca** şunları görür:
- kendi alanı,
- bağımlılık (dependency) bağlamı,
- minimal global state.

Kalıcı ortak durum **Proje Hafızası**'nda tutulur (CLAUDE.md Bölüm 8): aktif PRD, mimari kararlar (ADR), DAG durumu, ortak sözlük, kalite skorları.

---

## 12. Event Bus (Production Upgrade — opsiyonel)

İleride mikroservis gibi kurulmak istenirse, ajanlar arası olay tabanlı iletişim (topic'ler, backpressure, DLQ ve tüm detaylar için bkz. **`ACP.md`** Bölüm 6):

```jsonc
// örnek olay — pseudo
{
  "event": "task_completed",
  "from": "usta",
  "to": "kaptan",
  "payload": {}
}
```

---

## 13. Production Sağlamlaştırmaları

> v1 tasarımını "demo" seviyesinden "üretim" seviyesine taşıyan kritik eklemeler.

1. **Dinamik yeniden planlama (replan):** Bir node `failure`/`next_handoff` döndürdüğünde Kaptan DAG'ı çalışma anında yeniden kurar; tek hata tüm akışı kilitlemez.
2. **Retry + idempotency:** Her node'a retry politikası (exponential backoff) ve idempotency key — yeniden çalıştırma yan etkileri tekrarlamaz.
3. **Durable state / checkpoint:** DAG ortasında çökme olursa kaldığı yerden devam (durable execution). İmplementasyonda **LangGraph + Postgres checkpointer** bunu sağlar (bkz. `STACK.md`).
4. **Loop durma kriteri:** MODE 3 için `max_iterations` + iyileşme deltası eşiği (Bölüm 10).
5. **Bütçe yöneticisi (token/cost governor):** Skill başına `token-maliyeti` etiketine ek olarak **global bütçe**; aşılınca Kaptan akışı küçültür/durdurur.
6. **Ağırlıklı validation + hard/soft gate:** Bölüm 8'de uygulandı.
7. **Bağımsız güven skoru:** Ajanın self-report `confidence`'ı bağlayıcı değil; **Gözcü** bağımsız kalite skoru üretir (`cikti-kalite-skorlama`).
8. **Güvenlik & izolasyon:**
   - **Yetki kapsamı:** Her ajanın izinleri sınırlı (Usta kod yazar, Dedektif web'e çıkar; biri diğerinin yetkisini kullanamaz).
   - **Prompt injection savunması:** Dedektif'in topladığı web verisi *güvenilmez girdidir*; başka ajana verilmeden önce sanitize/izole edilir.
9. **Schema Registry:** `expected_output: "schema_ref"` versiyonlu bir şema kayıt defterine işaret eder; sözleşmeler merkezi ve versiyonlu tutulur.
10. **Human-in-the-loop kapısı:** Geri alınamaz işlemler (deploy, ödeme, veri silme) için kullanıcı onayı gerektiren özel node tipi.

---

## 14. Final Mimari (Özet)

Bu spesifikasyon olgunlaştığında sistem şunları sağlayacak:

- ✔ DAG tabanlı orkestrasyon
- ✔ Skill-güdümlü yönlendirme (routing)
- ✔ Ajan izolasyonu (sadece zarfı görür)
- ✔ Sözleşme tabanlı yürütme (Skill Contract + Message Envelope)
- ✔ Ağırlıklı validation pipeline (hard/soft gate)
- ✔ Çok modlu yürütme (sıralı / paralel / döngü)
- ✔ Dinamik replan, retry, durable checkpoint
- ✔ Bütçe yönetimi + güvenlik/izolasyon + human-in-the-loop

> **Durum (v1.3):** Sistem çalışıyor. Tool Runtime (8001) + Control-plane (8000) + Agent Studio UI (3000) + Observer (8002) prodüksiyona hazır. DAG yürütme, tool adapter, circuit breaker, compensation ledger, human-in-the-loop ve observability plane (KPI/score/cluster/recommendation) tamamen implemente edildi.

---

## 15. v1.1–v1.2 İmplemente Edilen Bileşenler

### Tool Runtime (services/tool-runtime, port 8001)
- **ToolAdapter Protocol** (`typing.Protocol`, `@runtime_checkable`): `execute / compensate / healthcheck / capabilities / validate_args`
- **ADAPTER_REGISTRY**: `build_registry(catalog)` lazy-import; ERP/WhatsApp sırları yoksa `SimulatedAdapter` fallback
- **Secrets Layer** (`secrets.py`): tek `os.environ` erişim noktası; API key değerleri asla loglanmaz
- **ERPAdapter**: BizimHesap/Logo/Netsis/Mikro `ERPProvider` enum; dry_run + real HTTP dispatch + DELETE compensation
- **WhatsAppAdapter**: graph.facebook.com/v19.0; non-reversible compensation
- **Circuit Breaker**: Redis-persisted `CLOSED→OPEN→HALF_OPEN`; `fail_threshold=5`, `recovery=60s`, `CIRCUIT_OPEN` ErrorCode (non-retryable)
- **FastAPI HTTP API**: `GET /health`, `GET /health/adapters`, `GET /tools/capabilities`, `POST /compensations/{exec_id}/apply`
- **Dual-mode**: NATS consumer + HTTP server aynı process (`asyncio.create_task`)

### Agent Studio UI (apps/web, port 3000)
- **Tailwind + shadcn/ui**: dark theme CSS vars, `globals.css`, `cn()` utility
- **TanStack Query**: typed API layer (`lib/api.ts`), `refetchInterval` polling (2–4s)
- **React Flow (`@xyflow/react`)**: otomatik topolojik layout (BFS layering), animasyonlu kenarlar, inline Onayla butonu
- **5 ekran**: Studio (goal input + 3-kolon task grid), Görevler listesi, Task Detail (DAG|Timeline split view), Tool Center (adapter health + capabilities), Hafıza Explorer (recall + tablo), Observer Dashboard (v1.3, §16)

---

## 16. v1.3 Observer — Observability Plane `[SPEC v1.3.0]`

Observer, sistemin kendi davranışını ölçen **post-hoc analytics plane**'idir. Execution
path'e dahil değildir — ayrı bir sidecar servistir (`services/observer`, port 8002).

```
Execution Plane          Observability Plane       Control Plane
  Planner                  Observer :8002 ──────►  /observer/* proxy
  Tool Runtime  ──► DB ──► (read-only)              (auth + routing)
  PostgreSQL                                               │
                                                    Agent Studio Dashboard
```

### Invariants (değişmez)
1. **Read-only:** Observer execution state'e YAZMAZ; dış çağrı (NATS/HTTP POST) YAPMAZ.
2. **Bounded queries:** Her sorgu window'a bağlı + `LIMIT 10k`. Tek geçit `db.bounded_query()`
   `WHERE created_at >= :since` + `LIMIT`'i otomatik enjekte eder — ham `execute()` yok.
   `SPEC_HASH` (`observer/__init__.py`) plan dosyasının sha256'sı; drift/regression baseline.

### 9 KPI (mevcut tablolardan, windowed 1h/24h/7d)
`workflow_success_rate`, `avg_workflow_duration_s`, `planner_error_rate`, `retry_coverage`,
`retry_pressure`, `dlq_rate`, `tool_reliability`, `memory_reuse_success`, `compensation_rate`.
- **MIN_SAMPLES (50) fallback:** birincil örneklem azsa window büyür (1h→24h→7d).
- **task_nodes'ta `created_at` yok** → `tasks` join, `tasks.created_at` ile window.

### Scoring
- `tool_reliability`: Bayesian smoothing (Jeffreys α=β=1) + invocation-count weighted avg.
- `retry_health = 1/(1+retry_pressure)` (nonlinear decay).
- `overall = 0.35·workflow + 0.30·tool + 0.20·planner + 0.15·retry_health`.
- **Anomaly delta** (1h/7d vs 24h baseline): yalnız her iki window'da MIN_SAMPLES varsa VE
  effective window'lar farklıysa (fallback collapse → `null`).

### Clustering & Recommendations
- Rule-based failure clusters (CIRCUIT_OPEN, RATE_LIMIT, ERP_TRANSIENT, SCHEMA_ERROR, …);
  `cluster_strength = count_10min / unique_tasks_10min`; >3/10dk → severity escalation.
- Advisory recommendations (eşik tabanlı) + `linked_kpis` correlation. **v1.3: pasif/görünür**;
  planner prompt'una enjeksiyon → v1.4 (Advise fazı).

### API & Cache
- `GET /health` (auth'suz) · `/scores` · `/clusters` · `/recommendations` · `/raw` (cache bypass).
- Service auth: `X-Internal-Token` (control-plane proxy enjekte eder).
- In-process snapshot cache, TTL 30s, key = `sha256(endpoint + canonical_qs)`.

> **v1.4'e ertelenenler:** statistical confidence layer, retry causality, cross-cluster
> correlation, HMAC/rotating token, advisory→planner injection, cause-chain visualization.

---

## 17. v1.3.1 UI Design System (Agent Studio Premium)

Agent Studio (`apps/web`) admin-panel'den premium SaaS dashboard'a yükseltildi.

### Tema & Tipografi
- **next-themes** (`attribute="class"`): dark + light, CSS-var iki palet (`globals.css`:
  `:root` light, `.dark` dark). Toggle sidebar'da; tercih localStorage'da kalıcı; FOUC yok
  (`suppressHydrationWarning` + `disableTransitionOnChange`).
- **Inter** (`next/font/google`, `--font-inter`) — self-hosted, layout-shift yok.
- **Semantic token invariant:** Hiçbir bileşen hardcoded dark-only renk (`*-950/*-400`)
  kullanmaz; tüm renkler token (`bg-card`, `text-foreground`, `bg-success`, `text-warning` …)
  üzerinden → light/dark otomatik. Recharts/React Flow renkleri `hsl(var(--*))` ile çözülür.

### Layout
- **Sol sidebar** (`components/sidebar.tsx` + `app-shell.tsx`): logo, 5 nav (lucide ikon,
  `usePathname` aktif state), tema toggle + versiyon. Desktop sticky grid; mobilde
  framer-motion drawer (hamburger + backdrop).

### Design System (CVA) — `app/components/ui/`
- `button` (primary/secondary/ghost/outline/destructive + loading), `card` (shadow + hover lift),
  `badge` (success/warning/info/danger/neutral), `table` (sticky header, hover row),
  `skeleton` (shimmer), `theme-toggle`. `status-badge` → Badge + lucide ikon, status→variant map.

### Motion & Görselleştirme
- **framer-motion**: kart stagger giriş (`fade-in/slide-up`), mobil drawer spring.
- **Recharts** (Observer): tool-reliability yatay BarChart (eşik çizgisi 0.80, renk token'lı
  Cell) + 3-window (1h/24h/7d) overall-score LineChart. Tema değişince renkler yeniden çözülür.

> Tag: `v1.3.1-premium-ui`. Backend roadmap'i etkilemez; v1.4 Observer Advise sırasında kalır.

---

## 18. v2.0-A Real Agents (LLM-powered reasoning)

Bu milestone'a kadar `agent-runner` reasoning düğümleri **stub**'tı (`"<skill> draft for: <goal>"`).
v2.0-A bunu gerçek LLM çağrısına dönüştürür — ajanlar artık gerçek içerik (mimari, kod, PRD) üretir.
**Henüz dosya yazma/build yok**; sadece artifact'lar (v2.0-B+ workspace ekler).

### Akış
```
ACP.TASK.CREATED → agent-runner consumer.handle()
  → _collaborate(task)  [async]
      ├─ LLM kapalı VEYA test bayrağı → _stub_collaborate (deterministik, eski davranış)
      └─ aksi halde → _llm_collaborate → llm.complete() (LiteLLM httpx)
            producer    : upstream artifact'lar + skill prompt → JSON artifact
            critic      : hedef artifact → {score, issues, suggestions}
            synthesizer : drafts + critiques → consensus
```

### Bileşenler
- **`runner/llm.py`**: LiteLLM `/v1/chat/completions` httpx client (planner.py deseni).
  `LLM_AVAILABLE` false veya her hata/timeout → `None` (çağıran stub'a düşer).
- **`runner/prompts.py`**: skill→uzman sistem prompt'u + JSON çıktı şeması registry
  (generic fallback). `build_producer/critic/synthesizer_messages`; upstream artifact'lar
  "ÖNCEKİ ADIMLARIN ÇIKTILARI" bloğu olarak kullanıcı mesajına enjekte (context passing).
- **`consumer.py` `_collaborate`**: artık `async`; test-mode gating + 3 rol + fallback.

### Invariant'lar (korunur)
- **Test-mode gating:** `stable_output/scores/base_score/score_step/fail_*` girdilerinden biri
  varsa stub yoluna gidilir → mevcut v0.6 retry/DLQ + v0.7 convergence acceptance'ları **aynen geçer**.
- **Graceful degradation:** Anahtar yoksa/LLM düşse bile sistem çökmez; stub üretir.
- **Provenance:** critic producer artifact'ını değiştirmez; single-writer snapshot (v0.7).

### Görüntüleme
- `GET /tasks/{id}/artifacts` (control-plane) — snapshot'tan düzleştirilmiş artifact listesi.
- Agent Studio Task Detail → **Artifacts paneli** (`tasks/[id]/_artifacts.tsx`): markdown,
  `files` kod blokları (collapsible), kararlar; stub içerik "stub" rozetiyle işaretlenir.

> Tag: `v2.0a-real-agents`. Önkoşul: gerçek LLM doğrulaması için `.env`'e API anahtarı.
> Sonraki: v2.0-B (workspace + dosya yazma + app-builder ajanları).

---

## 19. v2.0-B App Builder (artifact → çalıştırılabilir repo)

Kategori değişimi: code generation → **deterministic repo factory**. Çıktı artık artifact değil,
**çalışan sistem**. **İlke:** yapı deterministik kod; içerik LLM; **bütünlük Build Validator ile garanti**.

### Stack (tek, deterministik)
Next.js (App Router, TS) + **Prisma + SQLite**. Sebep: tek süreç + file-based routing (entry
wiring ~null) + zero-infra. Problem "multi-service orchestration" değil → **"single repo correctness"**.

### Akış
```
app-build DAG (deterministik şekil, LLM bypass; içerik gerçek LLM):
  app-spec → mimari → prisma-sema → nextjs-sayfa → nextjs-api
        ↓ artifact'lar (content.files, Next.js+Prisma yolları)
[Project Assembler]  scripts/assemble_repo.py  (DETERMİNİSTİK)
  1. Workspace: config/stacks/nextjs-prisma-sqlite/ scaffold (render)
  2. File placement: namespace ownership (prisma/ app/ app/api/), korumalı scaffold
  3. Dependency Synthesizer (2-faz): import çıkar + RULE-BASED resolve (alias→internal,
     builtin hariç, base-deps her zaman) → package.json
  4. Schema (tek-kaynak): prisma-sema model'leri → schema.prisma (concat değil)
[Build Validator]  scripts/build_validator.py  (STRICT, build-ÖNCESİ)
  A) yapısal: package.json, import graph, entry, route export, prisma id/relation
  B) semantik: route→model (prisma.X şemada var mı), fetch→endpoint, model kullanımı
        ↓ (GEÇERSE)
generated/<id>/ → npm install && npx prisma db push && npm run dev → ÇALIŞIR
```

### File Ownership Contract
Her app-builder skill ayrık path namespace'ine yazar (prompt dayatır, assembler doğrular):
`prisma-sema-uretici→prisma/`, `nextjs-sayfa-uretici→app/page+components`, `nextjs-api-uretici→app/api/`.
Çakışma yapısal olarak imkânsız; scaffold altyapı dosyaları (package.json, layout, lib/prisma) korumalı.

### Mimari konum (LLM ↔ deterministik ayrım)
- **LLM = semantic compiler frontend**: ne üretileceğini (sayfa/route/şema içeriği) üretir.
- **Assembler + Validator = deterministic backend**: yapıyı kurar, bütünlüğü statik garanti eder.
  LLM'in ürettiği hiçbir şey validator'dan geçmeden "runnable" sayılmaz.

> Tag: `v2.0b-app-builder`. Doğrulama: B1–B10 (assemble + validator + npm install/prisma/dev +
> validator negatif + cold-start + v2.0-A regresyon) yeşil.
> Sonraki: v2.1 (runtime workspace), v2.2 (build sandbox), v2.3 (live preview).
