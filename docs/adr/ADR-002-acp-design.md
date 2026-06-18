# ADR-002 — Agent Communication Protocol (ACP) Tasarımı

- **Durum:** Kabul edildi
- **Tarih:** 2026-06-18
- **İlgili:** `ACP.md`

## Bağlam
Ajanların güvenilir, izlenebilir ve izole biçimde haberleşmesi gerekiyor. Doğrudan ajan-ajan çağrısı, mimariyi bulanıklaştırır ve hata ayıklamayı imkânsızlaştırır.

## Karar
- Event-driven, sözleşme-öncelikli (contract-first) bir protokol: **ACP** (bkz. `ACP.md`).
- Standart **Message Envelope**; tipler: task/result/handoff/error/sync/ack/cancel/approval.
- **Trace sistemi:** tek `trace_id`, `parent_id`/`in_reply_to` zinciri; orphan mesaj yasak.
- **NATS JetStream subject'leri sabit:** `ACP.TASK.CREATED`, `ACP.TASK.COMPLETED`, `ACP.TASK.FAILED`, `ACP.HANDOFF.REQUESTED`, `ACP.AGENT.HEARTBEAT`, `ACP.SYSTEM.EVENT`.

## Mimari Kuralı (guardrail)
Akış **tek yönlü ve tek backend** üzerinden: `Web → FastAPI (control-plane) → NATS → Agents`.
- Next.js **API routes KULLANILMAZ**; tüm backend mantığı control-plane'dedir.
- Ajanlar birbirini doğrudan çağırmaz; yalnızca Kaptan/bus üzerinden.

## Sonuçlar
- (+) Tam observable, debuggable execution graph.
- (+) İsim/sözleşme sabitliği → erken refactor maliyeti yok.
- (−) Her iletişim bus'tan geçer; küçük işlerde ekstra hop. Kabul edilen takas.
