from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentic:agentic_dev_pw@postgres:5432/agentic_os"
    redis_url: str = "redis://redis:6379/0"
    nats_url: str = "nats://nats:4222"
    qdrant_url: str = "http://qdrant:6333"
    litellm_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-local-master-dev"
    llm_model: str = "claude-sonnet"  # LiteLLM model alias (env: LLM_MODEL)

    # Graceful degradation bayrakları (setup tarafından ayarlanır)
    llm_available: bool = False
    memory_available: bool = False
    observability_available: bool = False

    config_path: str = "/app/config/agents.json"
    tool_runtime_url: str = "http://tool-runtime:8001"  # v1.1-b: HTTP API proxy
    observer_url: str = "http://observer:8002"  # v1.3: analytics plane proxy
    observer_internal_token: str = "dev-internal-token"  # service-to-service auth


settings = Settings()
