# ADR-003 — Hafıza Stratejisi

- **Durum:** Kabul edildi
- **Tarih:** 2026-06-18
- **İlgili:** `CLAUDE.md` Bölüm 8, `STACK.md` Bölüm 4

## Bağlam
Ajanların hem yapısal (PRD, ADR, görev durumu, trace) hem de anlamsal (geçmiş içerik recall, benzerlik) hafızaya ihtiyacı var. Tek bir depo ikisini de iyi yapamaz.

## Karar
İki katmanlı **Proje Hafızası**:
- **PostgreSQL — yapısal hafıza:** aktif PRD, mimari kararlar, görev DAG durumu, ortak sözlük, kalite skorları, trace kayıtları. Tek doğruluk kaynağı.
- **Qdrant — anlamsal hafıza:** embeddings, RAG recall, benzerlik araması. `memory` profilinde opsiyonel.

Qdrant zorunlu değildir: `memory` profili kapalıyken control-plane `MEMORY_AVAILABLE=False` ile çalışır.

## Sonuçlar
- (+) Her depo güçlü olduğu işi yapar; ilk kurulum hafif (Qdrant opsiyonel).
- (−) İki sistem arası tutarlılık yönetimi gerekir (yazma sırası: önce Postgres, sonra Qdrant).
