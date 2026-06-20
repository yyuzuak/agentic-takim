#!/usr/bin/env bash
# v2.0-A Real Agents — canlı acceptance harness (RA1–RA5 + A7 regresyon).
# Gerçek LLM çıktısının üretildiğini, stub OLMADIĞINI ve context passing'i doğrular.
# Kullanım: CP=http://localhost:8000 bash scripts/verify_real_agents.sh
set -u
CP="${CP:-http://localhost:8000}"
TALLY="$(mktemp)"  # subshell'lerden (pipe) sayım için ortak dosya
note() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()   { echo "  ✓ $1"; echo P >> "$TALLY"; }
bad()  { echo "  ✗ $1"; echo F >> "$TALLY"; }

# POST hedef → task_id; düğümler done/failed olana dek bekle (max ~90s)
run_task() {
  local body="$1" tid
  tid=$(curl -s -X POST "$CP/tasks" -H 'Content-Type: application/json' -d "$body" \
        | python3 -c "import sys,json;print(json.load(sys.stdin).get('task_id',''))")
  [ -z "$tid" ] && { echo ""; return; }
  for _ in $(seq 1 45); do
    st=$(curl -s "$CP/tasks/$tid" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
    [ "$st" = "done" ] || [ "$st" = "failed" ] && break
    sleep 2
  done
  echo "$tid"
}
artifacts() { curl -s "$CP/tasks/$1/artifacts"; }

# ---------------------------------------------------------------- RA1 -------
note "RA1 — Basit bir CRM sistemi tasarla (mimari kalitesi)"
TID=$(run_task '{"goal":"Basit bir CRM sistemi tasarla","actor":"ra1"}')
if [ -z "$TID" ]; then bad "RA1 task oluşmadı"; else
  artifacts "$TID" | python3 -c "
import sys,json
d=json.load(sys.stdin)
arts=d['artifacts']
# mimari benzeri artifact: agent=mimar veya markdown alanı olan
arch=[a for a in arts if a.get('content') and (a['agent']=='mimar' or 'markdown' in (a.get('content') or {}))]
target=arch[0] if arch else (arts[-1] if arts else None)
import re
def emit(ok,msg): print(('OK::' if ok else 'BAD::')+msg)
if not target: emit(False,'mimari artifact yok')
else:
  c=target['content']; md=c.get('markdown') or c.get('summary') or json.dumps(c,ensure_ascii=False)
  txt=json.dumps(c,ensure_ascii=False)
  emit('draft for:' not in txt, 'stub pattern yok')
  emit(len(md)>=400, f'içerik uzunluğu yeterli ({len(md)}≥400)')
  secs=len(c.get('decisions') or []) + len(re.findall(r'(?m)^#{1,6}\s', md)) + md.count('\n## ')
  emit(secs>=3, f'≥3 bölüm/karar ({secs})')
" | while IFS= read -r l; do case "$l" in OK::*) ok "${l#OK::}";; BAD::*) bad "${l#BAD::}";; esac; done
fi

# ---------------------------------------------------------------- RA2 -------
note "RA2 — React tabanlı görev takip uygulaması oluştur (kod üretimi)"
TID=$(run_task '{"goal":"React tabanlı görev takip uygulaması oluştur","actor":"ra2"}')
if [ -z "$TID" ]; then bad "RA2 task oluşmadı"; else
  artifacts "$TID" | python3 -c "
import sys,json
d=json.load(sys.stdin); arts=d['artifacts']
code=[a for a in arts if a.get('content') and ('files' in (a.get('content') or {}) or a['agent']=='usta')]
target=code[0] if code else None
def emit(ok,msg): print(('OK::' if ok else 'BAD::')+msg)
if not target: emit(False,'kod artifact yok')
else:
  c=target['content']; txt=json.dumps(c,ensure_ascii=False)
  files=c.get('files') or {}
  emit('draft for:' not in txt,'stub pattern yok')
  emit(bool(files) or len(txt)>300, f'kod/dosya içeriği var (files={len(files)})')
" | while IFS= read -r l; do case "$l" in OK::*) ok "${l#OK::}";; BAD::*) bad "${l#BAD::}";; esac; done
fi

# ---------------------------------------------------------------- RA3 -------
note "RA3 — ERP teklif sistemi oluştur (çok-ajan + context passing)"
TID=$(run_task '{"goal":"ERP teklif sistemi oluştur","actor":"ra3"}')
if [ -z "$TID" ]; then bad "RA3 task oluşmadı"; else
  artifacts "$TID" | python3 -c "
import sys,json,re
d=json.load(sys.stdin); arts=[a for a in d['artifacts'] if a.get('content')]
def emit(ok,msg): print(('OK::' if ok else 'BAD::')+msg)
agents={a['agent'] for a in arts}
emit(len(agents)>=3, f'≥3 farklı ajan artifact üretti ({len(agents)}: {sorted(agents)})')
# context passing: upstream'deki belirgin terimler downstream'de geçiyor mu?
def words(a):
    t=json.dumps(a.get('content'),ensure_ascii=False).lower()
    return set(re.findall(r'[a-zçğıöşü]{5,}', t))
if len(arts)>=2:
    up=words(arts[0]); down=words(arts[-1])
    common=[w for w in (up & down) if w not in ('uygulama','sistem','proje','içerik','başlık','model')]
    emit(len(common)>=1, f'downstream upstream terimlerini referansl(ıyor) ({len(common)} ortak terim)')
else:
    emit(False,'context passing için yeterli artifact yok')
" | while IFS= read -r l; do case "$l" in OK::*) ok "${l#OK::}";; BAD::*) bad "${l#BAD::}";; esac; done
fi

# ---------------------------------------------------------------- RA4 -------
note "RA4 — Observer LLM akışlarını yansıtıyor (workflow_success_rate)"
curl -s "$CP/observer/scores?window=1h" | python3 -c "
import sys,json
d=json.load(sys.stdin)
def emit(ok,msg): print(('OK::' if ok else 'BAD::')+msg)
wsr=d.get('scores',{}).get('workflow_score')
emit(wsr is not None, f'workflow_score mevcut ({wsr})')
emit(d.get('samples',0)>=1, f'örneklem var ({d.get(\"samples\")})')
print('NOTE:: reasoning≠tool → tool_reliability yansıtmaz (beklenen)')
" | while IFS= read -r l; do case "$l" in OK::*) ok "${l#OK::}";; BAD::*) bad "${l#BAD::}";; NOTE::*) echo "  · ${l#NOTE::}";; esac; done

# ---------------------------------------------------------------- A7 --------
note "A7 regresyon — test-mode gating (fail_times → retry, stub yolu)"
TID=$(run_task '{"goal":"retry testi","skill":"prd-uretici","inputs":{"fail_times":2},"max_retries":3,"actor":"a7"}')
if [ -z "$TID" ]; then bad "A7 task oluşmadı"; else
  curl -s "$CP/tasks/$TID" | python3 -c "
import sys,json
d=json.load(sys.stdin); n=(d.get('nodes') or [{}])[0]
def emit(ok,msg): print(('OK::' if ok else 'BAD::')+msg)
emit(d.get('status')=='done' and n.get('retry_count')==2, f\"retry/DLQ korunuyor (status={d.get('status')}, retry={n.get('retry_count')})\")
" | while IFS= read -r l; do case "$l" in OK::*) ok "${l#OK::}";; BAD::*) bad "${l#BAD::}";; esac; done
fi

PASS=$(grep -c P "$TALLY" 2>/dev/null); PASS=${PASS:-0}
FAIL=$(grep -c F "$TALLY" 2>/dev/null); FAIL=${FAIL:-0}
rm -f "$TALLY"
note "SONUÇ: $PASS geçti, $FAIL başarısız"
[ "$FAIL" -eq 0 ] && echo "✅ v2.0-A REAL AGENTS — DOĞRULANDI" || echo "❌ düzeltme gerekiyor"
exit "$FAIL"
