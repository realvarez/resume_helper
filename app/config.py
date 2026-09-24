from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Every kit is tailored to this market; there is no per-request country input.
TARGET_COUNTRY = "Canada"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Provider-agnostic; any LiteLLM-compatible model string works,
    # e.g. "gemini/gemini-3.8-flash", "openrouter/anthropic/claude-sonnet-4.5", "groq/llama-3.3-70b-versatile", "ollama/llama3.1")
    llm_model: str = "gemini/gemini-3.8-flash"
    llm_api_key: str | None = None
    llm_temperature: float = 0.4

    # Optional live company research
    tavily_api_key: str | None = None
    tavily_max_results: int = 4

    # App behaviour
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MB
    results_cache_size: int = 20  # how many generated kits to keep in memory
    request_timeout: int = 300  # seconds for the LLM call


@lru_cache
def get_settings() -> Settings:
    return Settings()

