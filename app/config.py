"""
VSM AI Agent – Application Configuration (Prisma + Supabase)
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "VSM AI Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── Supabase / Prisma ─────────────────────────────────────────────────────
    database_url: str = ""
    direct_url: str = ""

    # ── LLM Provider ─────────────────────────────────────────────────────────
    # Default: groq — highest free-tier rate limits (14,400 req/day), OpenAI-compatible API
    llm_provider: str = "groq"               # groq | openai | anthropic | ollama

    # Groq (preferred — fastest inference, generous rate limits)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"  # alternatives: mixtral-8x7b-32768, llama3-70b-8192

    # OpenAI (fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Anthropic (fallback)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Ollama (local fallback)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # ── LLM Tuning ────────────────────────────────────────────────────────────
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_timeout: int = 30

    # ── Confidence Tiers (PRD 3 §8.1) ─────────────────────────────────────────
    auto_execute_threshold: float = 0.85
    ask_user_threshold: float = 0.60

    # ── Backend Communication ──────────────────────────────────────────────────
    backend_url: str = "http://localhost:8000"
    backend_timeout: int = 20
    ai_service_user_id: int = 0

    # ── Redis (context cache) ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/3"
    context_cache_ttl: int = 300


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
