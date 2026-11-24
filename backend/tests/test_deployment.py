import pytest
from pydantic import ValidationError

from backend.app.config import ROOT, Settings
from backend.app.db import Database


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


def test_production_supabase_uses_its_existing_cache_for_both_scopes():
    settings = production_settings(llm_enabled=True, openai_api_key="test", openai_model="test",
                                   service_access_token="test", database_url="sqlite:///:memory:")
    db = Database(settings)
    try:
        assert db.comparison_session is db.detail_session
        assert db.comparison_session is not db.session
        assert db.comparison_session.kw["bind"].get_execution_options()["schema_translate_map"] == {None: "analysis_cache"}
    finally:
        db.dispose()


def test_paid_llm_requires_access_control_unless_public_access_is_enabled():
    with pytest.raises(ValidationError, match="access control"):
        production_settings(llm_enabled=True, openai_api_key="test", openai_model="test",
                            service_access_token="")
    settings = production_settings(llm_enabled=True, llm_public_access=True,
                                   openai_api_key="test", openai_model="test")
    assert not settings.llm_auth_required


def test_demo_production_still_requires_a_persistent_database():
    with pytest.raises(ValidationError, match="persistent database"):
        production_settings(data_mode="demo")


def test_production_never_seeds_on_start():
    with pytest.raises(ValidationError, match="imports must run explicitly"):
        production_settings(seed_on_start=True)
