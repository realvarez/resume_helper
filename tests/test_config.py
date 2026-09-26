from app.config import TARGET_COUNTRY, Settings, get_settings


def test_target_country_is_canada():
    assert TARGET_COUNTRY == "Canada"


def test_default_settings_fields():
    fields = Settings.model_fields
    assert fields["llm_model"].default == "gemini/gemini-3.8-flash"
    assert fields["llm_temperature"].default == 0.4
    assert fields["max_upload_bytes"].default == 5 * 1024 * 1024
    assert fields["results_cache_size"].default == 20
    assert fields["request_timeout"].default == 300
    assert fields["tavily_max_results"].default == 4


def test_settings_override():
    settings = Settings(_env_file=None, llm_model="custom/model", results_cache_size=50)
    assert settings.llm_model == "custom/model"
    assert settings.results_cache_size == 50


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
