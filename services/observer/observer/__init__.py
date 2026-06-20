"""Observer — v1.3 observability kernel (post-hoc analytics plane).

SPEC FROZEN: bu servis dondurulmuş bir spesifikasyona göre yazılmıştır.
Yeni özellik = v1.4. SPEC_HASH, plan dosyasının (her-ajana-bir-isim-buzzing-thimble.md)
sha256'sıdır; drift/regression baseline olarak kullanılır.

Observer invariants:
  1. observe + score + recommend; ASLA execution state'e yazma veya dış çağrı yapma.
  2. Her sorgu window'a bağlı ve LIMIT'lidir (no full table scan).
"""

SPEC_VERSION = "v1.3.0"
SPEC_HASH = "2394acdf6ad4dc0ec60bcc1d55a92b2048c261e709d7b70e389b3492c6681429"
