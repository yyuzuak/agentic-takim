"""Secrets Layer — v1.1-a

Tek os.environ erişim noktası. Tool handler'lar context.secrets["key"]
ile erişir — env var adını bilmez. Audit: secret_accessed=True loglanır,
değer asla yazılmaz.
"""
from __future__ import annotations

import os

# Adapter adı → env var mapping (değer değil, anahtar adı)
_ADAPTER_KEYS: dict[str, dict[str, str]] = {
    "whatsapp": {
        "token":        "WHATSAPP_TOKEN",
        "phone_number_id": "WHATSAPP_PHONE_NUMBER_ID",
    },
    "erp": {
        "api_key":  "ERP_API_KEY",
        "base_url": "ERP_BASE_URL",
        "provider": "ERP_PROVIDER",
    },
}


class SecretResolver:
    def get(self, env_key: str) -> str:
        return os.environ.get(env_key, "")

    def inject(self, adapter_name: str) -> dict[str, str]:
        """Adapter için gereken secret'ları çöz. Boş string = ayarlanmamış."""
        mapping = _ADAPTER_KEYS.get(adapter_name, {})
        return {k: self.get(env_key) for k, env_key in mapping.items()}

    def available(self, adapter_name: str) -> bool:
        """Tüm kritik secret'lar set edilmişse True → gerçek adaptör kullanılabilir."""
        secrets = self.inject(adapter_name)
        # provider gibi optional field'lar default değer alabilir; boş = ayarlanmamış
        required = {k: v for k, v in secrets.items() if k not in ("provider",)}
        return bool(required) and all(v for v in required.values())


# Singleton
resolver = SecretResolver()
