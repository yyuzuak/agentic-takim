"""Skill prompt registry — gerçek ajan reasoning (v2.0-A).

Her skill'e uzmanlaşmış sistem prompt'u + çıktı şeması ipucu. Tanımsız skill'ler
generic fallback kullanır. Mesaj kurucuları upstream artifact'ları (context passing)
kullanıcı mesajına enjekte eder → downstream ajan upstream kararları görür.

Tüm üretici/sentezleyici prompt'lar LLM'den **JSON** ister (response_format json_object).
"""
from __future__ import annotations

import json
from typing import Any

# Çıktı şeması ipuçları (tekrar kullanım)
_CODE_OUT = '{"summary": "<bir cümle>", "files": {"<dosya/yol>": "<tam dosya içeriği>"}}'
_DOC_OUT = '{"markdown": "<markdown belge>", "decisions": ["<önemli karar>", ...]}'
_LIST_OUT = '{"markdown": "<markdown>", "items": ["<madde>", ...]}'

# skill → {system, output}
SKILL_PROMPTS: dict[str, dict[str, str]] = {
    "prd-uretici": {
        "system": "Sen kıdemli bir Ürün Yöneticisisin. Problem tanımı, JTBD, kullanıcı "
                  "hikâyeleri, kabul kriterleri ve başarı metrikleri içeren net bir PRD üret.",
        "output": _DOC_OUT,
    },
    "sistem-mimarisi-uretici": {
        "system": "Sen kıdemli bir Sistem Mimarısın. Teknoloji yığını seçimi, bileşen "
                  "diyagramı (metinsel), servis sınırları, veri akışı ve önemli mimari "
                  "kararları (ADR tarzı) içeren bir teknik tasarım üret. Pragmatik ol.",
        "output": _DOC_OUT,
    },
    "api-sozlesme-tasarimci": {
        "system": "Sen bir API tasarımcısısın. REST/GraphQL uç noktalarını, istek/yanıt "
                  "şemalarını ve hata kodlarını net biçimde tanımla.",
        "output": _DOC_OUT,
    },
    "veri-modelleme-motoru": {
        "system": "Sen bir veri modelleme uzmanısın. Varlıkları, ilişkileri, alanları ve "
                  "indeksleme stratejisini (ERD'yi metinsel) tanımla.",
        "output": _DOC_OUT,
    },
    "fullstack-kod-uretici": {
        "system": "Sen kıdemli bir full-stack mühendisisin. Verilen mimariye sadık kalarak "
                  "ÇALIŞAN, eksiksiz kod üret. Her dosyayı tam içeriğiyle ver; placeholder "
                  "veya '...' kullanma. Üst adımların teknoloji seçimlerine uy.",
        "output": _CODE_OUT,
    },
    "frontend-sistem-insaaci": {
        "system": "Sen bir frontend mühendisisin. Bileşen mimarisi ve state yönetimiyle "
                  "çalışan UI kodu üret. Tam dosya içerikleri ver.",
        "output": _CODE_OUT,
    },
    "backend-servis-insaaci": {
        "system": "Sen bir backend mühendisisin. API katmanı, servis mantığı ve veritabanı "
                  "entegrasyonuyla çalışan sunucu kodu üret. Tam dosya içerikleri ver.",
        "output": _CODE_OUT,
    },
    "test-cercevesi-uretici": {
        "system": "Sen bir test mühendisisin. Üretilen koda uygun unit/integration testleri "
                  "yaz. Tam test dosyaları ver.",
        "output": _CODE_OUT,
    },
    "derin-web-arastirma": {
        "system": "Sen bir derin araştırmacısın. Konuyu çok açıdan analiz eden, kaynaklı ve "
                  "yapılandırılmış bir araştırma özeti üret.",
        "output": _LIST_OUT,
    },
    "pazar-zekasi-motoru": {
        "system": "Sen bir pazar analistisisin. TAM/SAM/SOM, rakipler, fiyatlandırma ve "
                  "trend analizini özetle.",
        "output": _LIST_OUT,
    },
    "eda-motoru": {
        "system": "Sen bir veri bilimcisin. Hedefe uygun keşifçi veri analizi yaklaşımını, "
                  "varsayımları ve içgörü hipotezlerini özetle.",
        "output": _LIST_OUT,
    },
}

# ---- v2.0-B App Builder: stack-aware (Next.js App Router + Prisma + SQLite) ----
# File Ownership: her skill YALNIZ kendi namespace'ine yazar (assembler dayatır).

SKILL_PROMPTS.update({
    "app-spec-uretici": {
        "system": "Sen bir ürün analistisin. Verilen uygulama fikrini somut bir app spec'e "
                  "indirgersin: entity'ler (alanlarıyla), özellikler ve sayfa listesi.",
        "output": '{"markdown": "<özet>", "entities": [{"name": "Post", "fields": ["title:string", "body:string"]}], '
                  '"pages": ["/", "/posts/[id]"], "features": ["liste", "detay", "oluştur"]}',
    },
    "prisma-sema-uretici": {
        "system": "Sen bir Prisma uzmanısın. SADECE Prisma model blokları üret (datasource ve "
                  "generator EKLEME — onlar scaffold'da hazır). SQLite uyumlu. KURALLAR: her "
                  "model bir `id Int @id @default(autoincrement())` içermeli; ilişkilerde @relation "
                  "tutarlı olmalı; alan tipleri SQLite-uyumlu (String/Int/Boolean/DateTime/Float). "
                  "Ayrıca prisma/seed.ts üret (PrismaClient ile birkaç örnek kayıt).",
        "output": '{"files": {"prisma/_models.prisma": "model Post {\\n  id Int @id @default(autoincrement())\\n  ...\\n}", '
                  '"prisma/seed.ts": "<seed kodu>"}}',
    },
    "nextjs-sayfa-uretici": {
        "system": "Sen bir Next.js (App Router) frontend mühendisisin. SADECE app/**/page.tsx ve "
                  "app/components/** dosyaları üret. KURALLAR: App Router; veri çeken/etkileşimli "
                  "component'lerde dosya başına `'use client'`; veriyi yalnızca `/api/*` endpoint'lerinden "
                  "fetch et (doğrudan DB erişme); göreli değil mutlak `/api/...` yolları kullan. "
                  "Tam, çalışan TSX üret; placeholder yok.",
        "output": '{"files": {"app/page.tsx": "<tam tsx>", "app/components/PostList.tsx": "<tam tsx>"}}',
    },
    "nextjs-api-uretici": {
        "system": "Sen bir Next.js (App Router) backend mühendisisin. SADECE app/api/**/route.ts "
                  "dosyaları üret. KURALLAR: `import { prisma } from '@/lib/prisma'`; HTTP metodlarını "
                  "named export et (export async function GET/POST/...); `import { NextResponse } from 'next/server'` "
                  "kullan; yalnız prisma şemasında VAR OLAN model'leri kullan (uydurma). Tam, çalışan kod.",
        "output": '{"files": {"app/api/posts/route.ts": "<tam route>"}}',
    },
})

_GENERIC = {
    "system": "Sen bir uzman AI ajansın. Verilen göreve dair net, eyleme dönük ve "
              "yapılandırılmış bir çıktı üret.",
    "output": _DOC_OUT,
}


def _spec(skill: str | None) -> dict[str, str]:
    return SKILL_PROMPTS.get(skill or "", _GENERIC)


def _format_upstream(upstream: list[dict[str, Any]]) -> str:
    """Bağımlı düğümlerin artifact içeriklerini context bloğuna çevirir."""
    if not upstream:
        return ""
    parts = ["\n\n=== ÖNCEKİ ADIMLARIN ÇIKTILARI (bunlara dayan) ==="]
    for u in upstream:
        key, agent, content = u.get("node_key"), u.get("agent"), u.get("content")
        body = json.dumps(content, ensure_ascii=False, indent=2) if content is not None else "(boş)"
        parts.append(f"\n[{key} · {agent}]\n{body}")
    return "\n".join(parts)


def build_producer_messages(skill: str | None, goal: str, upstream: list[dict]) -> list[dict]:
    spec = _spec(skill)
    user = (
        f"GÖREV: {goal}\n"
        f"{_format_upstream(upstream)}\n\n"
        f"Yalnızca şu JSON şemasında yanıt ver (başka metin yok):\n{spec['output']}"
    )
    return [
        {"role": "system", "content": spec["system"] + " Yanıtın SADECE geçerli JSON olmalı."},
        {"role": "user", "content": user},
    ]


def build_critic_messages(skill: str | None, goal: str, target_content: Any) -> list[dict]:
    body = json.dumps(target_content, ensure_ascii=False, indent=2)
    user = (
        f"GÖREV BAĞLAMI: {goal}\n\n"
        f"İNCELENECEK ÇIKTI:\n{body}\n\n"
        "Bu çıktıyı eleştirel değerlendir. Yalnızca şu JSON ile yanıtla:\n"
        '{"score": <0.0-1.0>, "issues": ["<sorun>", ...], "suggestions": ["<öneri>", ...]}'
    )
    return [
        {"role": "system", "content": "Sen titiz bir teknik gözden geçiricisin (reviewer). "
                                       "Yapıcı ama dürüst ol. Yanıtın SADECE geçerli JSON."},
        {"role": "user", "content": user},
    ]


def build_synthesizer_messages(skill: str | None, goal: str, drafts: dict, critiques: list) -> list[dict]:
    user = (
        f"GÖREV: {goal}\n\n"
        f"TASLAKLAR:\n{json.dumps(drafts, ensure_ascii=False, indent=2)}\n\n"
        f"ELEŞTİRİLER:\n{json.dumps(critiques, ensure_ascii=False, indent=2)}\n\n"
        "Taslakları ve eleştirileri birleştirerek nihai konsensüs çıktısını üret. "
        f"Yalnızca şu JSON ile yanıtla:\n{_spec(skill)['output']}"
    )
    return [
        {"role": "system", "content": "Sen bir sentezleyicisin: birden çok uzman çıktısını "
                                       "ve eleştiriyi tek tutarlı sonuca indirgersin. Yanıtın SADECE JSON."},
        {"role": "user", "content": user},
    ]
