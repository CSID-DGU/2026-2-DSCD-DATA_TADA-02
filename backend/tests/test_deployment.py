import pytest
from pydantic import ValidationError

from backend.app.config import ROOT, Settings


def production_settings(**overrides):
    values = dict(
        app_env="production", data_mode="supabase", seed_on_start=False,
        supabase_database_url="postgresql+psycopg://unused:unused@localhost/postgres",
        supabase_sslrootcert=ROOT / "data/certificates/supabase-ca.crt",
        _env_file=None,
    )
    return Settings(**(values | overrides))


def test_read_only_supabase_deployment_does_not_require_a_writable_cache():
    settings = production_settings()
    assert not settings.llm_enabled and not settings.seed_on_start


def test_paid_llm_still_requires_a_persistent_cache():
    with pytest.raises(ValidationError, match="persistent database"):
        production_settings(llm_enabled=True, openai_api_key="test", openai_model="test",
                            service_access_token="test")


def test_demo_production_still_requires_a_persistent_database():
    with pytest.raises(ValidationError, match="persistent database"):
        production_settings(data_mode="demo")


def test_production_never_seeds_on_start():
    with pytest.raises(ValidationError, match="imports must run explicitly"):
        production_settings(seed_on_start=True)
