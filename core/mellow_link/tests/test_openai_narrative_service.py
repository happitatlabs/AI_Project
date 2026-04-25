from mellow_link.config.settings import Settings
from mellow_link.services.openai_narrative_service import OpenAINarrativeLLMService


def test_openai_narrative_service_reuses_single_model_for_all_modes():
    service = OpenAINarrativeLLMService(
        api_key="key",
        models={"thinking": "gpt-4o-mini"},
        timeout=15,
    )

    assert service.get_model_for_mode("thinking") == "gpt-4o-mini"
    assert service.get_model_for_mode("thinking-lite") == "gpt-4o-mini"
    assert service.get_model_for_mode("fast") == "gpt-4o-mini"
    assert service.get_model_for_mode("research") == "gpt-4o-mini"


def test_settings_narrative_llm_configured_for_openai_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    base = Settings().model_copy(
        update={
            "enable_narrative_llm": True,
            "narrative_llm_provider": "openai",
            "openai_api_key": "",
            "openai_narrative_model": "gpt-4o-mini",
        }
    )

    assert base.narrative_llm_provider_normalized == "openai"
    assert base.narrative_llm_api_key == "openai-key"
    assert base.narrative_llm_model == "gpt-4o-mini"
    assert base.narrative_llm_configured is True
