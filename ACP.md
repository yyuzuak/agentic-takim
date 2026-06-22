# ACP.md — Agent Communication Protocol (v1)

> ℹ️ **KAPSAM NOTU:** Bu belge ajanlar-arası iletişim protokolünün **tasarım spesifikasyonudur.** Bloklar kavramı anlatan **örnek şema / sözde-kod**tur. Protokol artık **gerçek runtime olarak implemente edilmiştir**: NATS JetStream üzerinde çalışan bir message bus + DLQ + retry mevcuttur (kanonik subject'ler `packages/schemas/agentic_schemas/events/v1.py` ve `scripts/init-nats.sh` ile sabittir; bkz. `ARCHITECTURE.md`). Ajan personaları için bkz. `CLAUDE.md`.

---

## 0. Tasarım İlkeleri

Protokol 5 temel prensibe dayanır:

1. **Determinism** — Aynı girdi → aynı **mesaj grafiği**.
2. **Traceability** — Her mesaj zincirlenebilir olmalı.
3. **Isolation** — Ajanlar birbirini doğrudan çağırmaz.
4. **Contract-first** — Şema olmadan iletişim yok.
5. **Event-driven** — Tüm iletişim event olarak akar.

> ⚠️ **Determinizm uyarısı (önemli):** "Aynı girdi → aynı sonuç" garantisi **yalnızca mesaj grafiğinin/routing yapısının** deterministik olduğu anlamına gelir — **içerik (LLM çıktısı) deterministik değildir.** İçeriği olabildiğince stabilize etmek için: mümkün olduğunda `temperature` düşürülür / `seed` sabitlenir, `determinizm` yüksek skill'ler tercih edilir (bkz. CLAUDE.md Bölüm 6). Mutlak tekrarlanabilirlik beklenmemelidir.

---

## 1. Core Message Format (Base Envelope)

Her mesaj bu zarfla taşınır:

```jsonc
// örnek şema — pseudo
{
  "protocol_version": "1.0",
  "schema_version": "1",          // YENİ: envelope/şema sürüm uyumu (bkz. Bölüm 11)

  "message_id": "uuid",
  "trace_id": "uuid",
  "parent_id": "uuid | null",
  "in_reply_to": "uuid | null",   // YENİ: bir result'ı tetikleyen task'a birebir bağ

  "from": "kaptan",
  "to": "mimar",

  "type": "task | result | handoff | error | sync | ack | cancel | approval_request | approval_response",

  "skill": "sistem-mimarisi-uretici",   // Türkçe skill id (CLAUDE.md ile tutarlı)

  "timestamp": 1710000000,        // epoch; sıralama için tek başına güvenilmez — trace içi sequence kullan

  "priority": "low | normal | high | critical",
  "trust": "trusted | untrusted", // YENİ: dış/scrape edilmiş veri 'untrusted' (bkz. Bölüm 10)

  "payload": {},
  "artifact_refs": [],            // YENİ: büyük çıktı inline değil, referansla (bkz. Bölüm 6)

  "context": {
    "compressed_state": "...",
    "global_constraints": [],
    "agent_memory_ref": "optional-key"   // Proje Hafızası'ndaki tam state'e işaret
  },

  "expected_output_schema": "schema_id",

  "ttl_ms": 300000,               // mesajın geçerlilik süresi
  "exec_timeout_ms": 120000       // YENİ: görev yürütme zaman aşımı (ttl'den ayrı kavram)
}
```

> **task_id / message_id / trace_id ilişkisi:** Bir **görev (task)** kendi `task_id`'sini taşır (ARCHITECTURE.md Bölüm 2/4 ile aynı düğüm). Her **mesajın** kendi `message_id`'si vardır. Bir iş akışındaki tüm görev ve mesajlar aynı `trace_id`'yi paylaşır.

---

## 2. Message Types

> 💡 Bu mesaj tipleri, `packages/schemas/agentic_schemas/acp/v1` içinde **tipli Pydantic modelleri** olarak da mevcuttur: `TaskMessage`, `ResultMessage`, `HandoffMessage`, `ErrorMessage`, `AckMessage`, `SyncMessage`, `CancelMessage`, `ApprovalRequestMessage`, `ApprovalResponseMessage`. Her biri `Envelope`'ı genişletir ve payload'u tiplidir.

### 2.1 TASK — iş başlatır
```jsonc
{ "type": "task", "from": "kaptan", "to": "mimar",
  "skill": "api-sozlesme-tasarimci",
  "payload": { "goal": "API tasarla", "inputs": {} } }
```

### 2.2 RESULT — sonuç döner
```jsonc
{ "type": "result", "from": "mimar", "to": "kaptan",
  "skill": "api-sozlesme-tasarimci", "in_reply_to": "task-msg-uuid",
  "payload": { "result": {}, "artifacts": [], "confidence": 0.92,
               "assumptions": [], "risks": [] } }
```
> `confidence` self-report'tur, bağlayıcı değildir; bağımsız skor **Gözcü** tarafından üretilir (Bölüm 4).

### 2.3 HANDOFF — devir (KRİTİK)
```jsonc
{ "type": "handoff", "from": "pusula", "to": "mimar",
  "reason": "teknik derinlik gerekiyor",
  "skill": "sistem-mimarisi-uretici",
  "payload": { "context_summary": "...", "open_questions": [] } }
```

### 2.4 ERROR — hata
```jsonc
{ "type": "error", "from": "usta", "to": "kaptan",
  "error_code": "SCHEMA",  // taksonomi: Bölüm 8
  "message": "Beklenen API spec'inde eksik alan: endpoints" }
```

### 2.5 ACK / SYNC — teyit / eşitleme
```jsonc
{ "type": "ack", "from": "mimar", "to": "kaptan", "status": "received" }
```

### 2.6 CANCEL — iptal / kesinti (YENİ)
Kullanıcı işi durdurduğunda veya Kaptan bir dalı öldürdüğünde (ör. bütçe aşımı).
```jsonc
{ "type": "cancel", "from": "kaptan", "to": "usta",
  "trace_id": "abc", "reason": "budget_exceeded | user_abort | superseded" }
```

### 2.7 APPROVAL — human-in-the-loop (YENİ)
Geri alınamaz işlemler (deploy, ödeme, veri silme) için kullanıcı onayı.
```jsonc
// istek
{ "type": "approval_request", "from": "usta", "to": "kaptan",
  "payload": { "action": "production-deploy", "impact": "irreversible", "details": {} } }
// yanıt
{ "type": "approval_response", "from": "kaptan", "to": "usta",
  "in_reply_to": "approval-req-uuid", "payload": { "approved": true } }
```

---

## 3. Trace System

Her iş akışı tek bir trace altında yaşar:

```
trace_id = USER_REQUEST_001
   ├── task_1 (dedektif)
   ├── task_2 (pusula)   parent_id = task_1
   ├── task_3 (mimar)    parent_id = task_2
   └── task_4 (usta)     parent_id = task_3
```

**Kurallar:**
- Her mesaj aynı `trace_id`'yi taşır.
- `parent_id` ile zincir kurulur; `in_reply_to` ile istek↔yanıt birebir eşlenir.
- **Orphan mesaj yasaktır** (parent'ı veya trace'i olmayan mesaj reddedilir).

---

## 4. Routing Protocol

Ajanlar birbirine **doğrudan konuşmaz**:

```
Agent → Kaptan → Agent
   veya
Agent → Event Bus → Kaptan → Agent
```

```python
# pseudo-code
def route(message):
    if message.skill not in agent(message.to).skills:
        return route_to("kaptan")   # fallback
    return deliver(message)
```

> **Gözcü (Observer) entegrasyonu (YENİ):** Gözcü routing yolunun **dışındadır**. Tüm topic'lere **salt-okunur abone**dir; mesajları izler, kalite skorlar, anomali yakalar ama akışı yönlendirmez. Bulgusunu yalnızca Kaptan'a `result`/`error` olarak iletir.

---

## 5. Context Compression Layer

Her mesajda bağlam küçültülür:

```
raw_context → semantic_filter → agent_relevance_filter → token_budget_optimizer → final_context
```

```jsonc
// örnek
{ "compressed_state": { "only_relevant_entities": true, "max_tokens": 800,
                        "removed_noise": ["chat history", "irrelevant tools"] },
  "agent_memory_ref": "proj-mem://prd/v3" }
```

> Bir ajan sıkıştırılmış bağlamı yetersiz bulursa, `agent_memory_ref` üzerinden Proje Hafızası'ndan **tam state genişletme** isteyebilir (CLAUDE.md Bölüm 8).

---

## 6. Event Bus

Sistem async çalışabilir.

**Topic'ler (kavramsal):** `task.created`, `task.completed`, `task.failed`, `handoff.requested`, `task.cancelled`, `agent.heartbeat`, `approval.requested`.

**Kanonik JetStream subject'leri (implementasyon — sabittir):** `init-nats.sh` ve `agentic_schemas.events.v1` ile birebir (9 subject). Sonradan değiştirmek pahalıdır:

```
ACP.TASK.CREATED      ACP.TASK.COMPLETED    ACP.TASK.FAILED
ACP.TASK.DLQ          ACP.TOOL.REQUEST      ACP.TOOL.RESULT
ACP.HANDOFF.REQUESTED ACP.AGENT.HEARTBEAT   ACP.SYSTEM.EVENT
```

```jsonc
{ "event": "task.completed", "trace_id": "abc", "from": "usta", "payload": {} }
```

**YENİ — Akış kontrolü:**
- **Backpressure:** `max_in_flight` (eşzamanlı iş), kuyruk uzunluk limiti, tüketici eşzamanlılığı; dış API hız limitleri uygulanır.
- **DLQ (Dead Letter Queue):** Retry'ı tükenen veya işlenemeyen mesaj kaybolmaz; incelenmek üzere DLQ'ya yazılır ve Kaptan/Gözcü'ye bildirilir.

---

## 7. Consistency Rules

- **7.1 Tek sorumluluk:** Bir mesaj = bir skill yürütmesi.
- **7.2 Çapraz çağrı yasağı:** ❌ Usta → Mimar doğrudan; ✔ yalnızca Kaptan üzerinden.
- **7.3 Idempotency + teslimat garantisi (YENİ):** Bus **at-least-once** teslim eder; `message_id` hash kontrolü ile çift mesaj yok sayılır ⇒ **effective-once**. Yan etkili işlemler idempotency key taşır.
- **7.4 Şema zorunluluğu:** Her skill çıktısı bir şemaya uymak zorundadır.
```jsonc
{ "schema_id": "api_contract_v1", "required_fields": ["endpoints", "auth"] }
```

---

## 8. Failure Model

**Retry:** transient hata → 3x exponential backoff. Tükenirse → **DLQ** (Bölüm 6).

**Hata taksonomisi (YENİ)** — her kod farklı yola gider:

| `error_code` | Anlam | Eylem |
|--------------|-------|-------|
| `TRANSIENT` | Geçici (ağ, rate limit) | Retry (backoff) |
| `SCHEMA` | Şema/sözleşme ihlali | Anında reddet (retry yok) |
| `LOGICAL` | Mantıksal/anlamsal hata | Kaptan'a handoff → replan |
| `PERMISSION` | Yetki dışı işlem | Reddet + Kaptan'a bildir |
| `BUDGET` | Token/maliyet bütçesi aşıldı | Akışı küçült/durdur (`cancel`) |
| `TIMEOUT` | `exec_timeout_ms` aşıldı | Retry veya replan |

---

## 9. Agent State Model

Her ajan **stateless** çalışır, ancak çalışma süresince:

```jsonc
{ "ephemeral_memory": {}, "active_trace": "uuid", "skill_cache": {} }
```

**YENİ — Liveness:** Ajanlar `agent.heartbeat` yayınlar. Heartbeat zaman aşımına uğrayan ajan **"takılı (stuck)"** sayılır; ilgili görev `blocked`/`failed`'a düşer ve Kaptan dalı **replan** eder (ARCHITECTURE.md Bölüm 13.1).

---

## 10. Security Layer

- **Mesaj imzalama:** HMAC / RSA ile bütünlük.
- **Tamper detection:** trace üzerinde değişiklik tespiti.
- **Permission scopes:** Ajan başına yetki kapsamı (Usta kod yazar, Dedektif web'e çıkar; biri diğerinin yetkisini kullanamaz).
- **YENİ — Untrusted payload sanitizasyonu:** `trust: "untrusted"` etiketli içerik (ör. Dedektif'in scrape ettiği web verisi) başka ajana verilmeden **sanitize/izole** edilir — prompt-injection savunması.

---

## 11. Schema Registry & Versioning (YENİ)

`expected_output_schema: "schema_id"` merkezi, **versiyonlu** bir kayıt defterine işaret eder.

```jsonc
// örnek registry kaydı
{ "schema_id": "api_contract", "version": "1",
  "required_fields": ["endpoints", "auth"], "compatible_with": ["1"] }
```

- Üretici ve tüketici şema sürümleri **uyumluluk kontrolünden** geçer; uyumsuzluk → `SCHEMA` hatası.
- Bu kayıt defteri ARCHITECTURE.md Bölüm 13.9 (Schema Registry) ile aynıdır.

---

## 12. Full Flow Example

**İstek:** "Bir SaaS ürün tasarla ve backend'i kodla."

```
trace_id = SaaS_001
1. KAPTAN     → niyet ayrıştırma (niyet-ayristirma)
2. DEDEKTİF   → pazar araştırması (pazar-zekasi-motoru)
3. PUSULA     → PRD (prd-uretici)
4. MİMAR      → mimari (sistem-mimarisi-uretici)
5. USTA       → backend kod (backend-servis-insaaci)
6. KAPTAN     → birleştirme + validation (yurutme-denetcisi)
        ⟂ GÖZCÜ tüm adımları salt-okunur izler, kalite skorlar.
```

Tüm mesajlar `trace_id = SaaS_001` paylaşır; her adım bir önceki adıma `parent_id` ile bağlanır.

---

## 13. Sonuç

ACP v1 (+ eklemeler) sistemi şuraya taşır:
- ✔ Tam gözlemlenebilir (observable) ajan sistemi
- ✔ Hata ayıklanabilir yürütme grafiği (trace + decision_trace)
- ✔ Mikroservis seviyesinde ayrışma (isolation)
- ✔ Geleceğe ölçeklenme (multi-node, dağıtık ajanlar)
- ✔ Sözleşme + güvenlik + dayanıklılık (DLQ, retry, idempotency, liveness)

> **Hatırlatma:** Bu protokol implemente edilmiştir — **NATS JetStream** üzerinde, **LangGraph** ajan runtime'ı ve **FastAPI** control plane ile hayata geçirildi (bkz. `STACK.md`, `ARCHITECTURE.md`).
