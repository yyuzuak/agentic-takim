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

> **Sonraki adım:** Stack seçildi (bkz. `STACK.md` — LangGraph tabanlı). Sırada bu spec'in çalışan koda dönüştürülmesi var. Henüz kod yazılmamıştır.
