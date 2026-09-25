from app.config import TARGET_COUNTRY, Settings, get_settings


def test_target_country_is_canada():
    assert TARGET_COUNTRY == "Canada"


def test_default_settings_without_env_file():
    # Pass _env_file=None to inspect code-defined defaults rather than local .env
    settings = Settings(_env_file=None)
    assert settings.llm_model == "gemini/gemini-3.8-flash"
    assert settings.llm_temperature == 0.4
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.results_cache_size == 20
    assert settings.request_timeout == 300
    assert settings.tavily_max_results == 4


def test_settings_override():
    settings = Settings(_env_file=None, llm_model="custom/model", results_cache_size=50)
    assert settings.llm_model == "custom/model"
    assert settings.results_cache_size == 50


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
