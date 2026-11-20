from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./tmp/service.db"
    data_mode: str = "demo"
    supabase_database_url: SecretStr | None = None
    supabase_sslrootcert: Path = Path("tmp/supabase-ca.crt")
    seed_on_start: bool = True
    llm_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = ""
    llm_timeout_seconds: float = Field(default=40, ge=1, le=90)
    llm_max_concurrent: int = Field(default=2, ge=1, le=8)
    llm_cache_ttl_seconds: int = Field(default=86400, ge=1)
    service_access_token: str = ""

    @model_validator(mode="after")
    def check_deployment(self):
        # The read-only Supabase service never uses the cache while LLM is disabled.
        cache_required = self.llm_enabled or self.data_mode != "supabase"
        if self.app_env == "production" and cache_required and self.database_url.startswith("sqlite"):
            raise ValueError("Production requires a persistent database for the explanation cache.")
        if self.app_env == "production" and self.seed_on_start:
            raise ValueError("Production imports must run explicitly, not on startup.")
        if self.llm_enabled and not (self.openai_api_key and self.openai_model):
            raise ValueError("LLM_ENABLED requires OPENAI_API_KEY and OPENAI_MODEL.")
        if self.app_env == "production" and self.llm_enabled and not self.service_access_token:
            raise ValueError("Paid LLM endpoints require server-side access control.")
        if self.data_mode not in {"demo", "supabase"}:
            raise ValueError("DATA_MODE must be demo or supabase.")
        if self.data_mode == "supabase":
            if not self.supabase_database_url or not self.supabase_database_url.get_secret_value().startswith("postgresql+psycopg://"):
                raise ValueError("DATA_MODE=supabase requires SUPABASE_DATABASE_URL with the psycopg driver.")
            if not (ROOT / self.supabase_sslrootcert).is_file():
                raise ValueError("Set SUPABASE_SSLROOTCERT to the Supabase root certificate file.")
        return self
