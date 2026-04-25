import pytest
from types import SimpleNamespace

from mellow_link.config.settings import Settings
from mellow_link.services.azure_openai_service import AzureOpenAILLMService


def test_azure_openai_service_reuses_single_narrative_model_for_all_modes():
    service = AzureOpenAILLMService(
        api_key="key",
        azure_endpoint="https://example.openai.azure.com/",
        api_version="2024-02-15-preview",
        models={"thinking": "gpt4o-mini"},
        timeout=15,
    )

    assert service.get_model_for_mode("thinking") == "gpt4o-mini"
    assert service.get_model_for_mode("thinking-lite") == "gpt4o-mini"
    assert service.get_model_for_mode("fast") == "gpt4o-mini"
    assert service.get_model_for_mode("research") == "gpt4o-mini"


def test_settings_narrative_llm_configured_requires_azure_values(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MELLOW_AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Settings().model_copy(
        update={
            "azure_openai_api_key": "",
            "openai_api_key": "",
            "azure_openai_endpoint": "",
            "azure_openai_narrative_model": "",
        }
    )
    configured = base.model_copy(
        update={
            "enable_narrative_llm": True,
            "narrative_llm_provider": "azure_openai",
            "azure_openai_api_key": "key",
            "azure_openai_endpoint": "https://example.openai.azure.com/",
            "azure_openai_narrative_model": "gpt4o-mini",
        }
    )
    unconfigured = base.model_copy(
        update={
            "enable_narrative_llm": True,
            "narrative_llm_provider": "azure_openai",
            "azure_openai_endpoint": "https://example.openai.azure.com/",
            "azure_openai_narrative_model": "gpt4o-mini",
        }
    )

    assert configured.narrative_llm_configured is True
    assert unconfigured.narrative_llm_configured is False


@pytest.mark.parametrize("env_key", ["OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"])
def test_settings_narrative_llm_api_key_accepts_openai_env_fallback(monkeypatch, env_key):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MELLOW_AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(env_key, "fallback-key")
    base = Settings().model_copy(
        update={
            "azure_openai_api_key": "",
            "openai_api_key": "",
        }
    )
    configured = base.model_copy(
        update={
            "enable_narrative_llm": True,
            "narrative_llm_provider": "azure_openai",
            "azure_openai_endpoint": "https://example.openai.azure.com/",
            "azure_openai_narrative_model": "gpt4o-mini",
            "azure_openai_api_key": "",
            "openai_api_key": "",
        }
    )

    assert configured.narrative_llm_api_key == "fallback-key"
    assert configured.narrative_llm_configured is True


def test_azure_openai_service_retries_with_max_completion_tokens():
    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def create(self, **kwargs):
            self.calls.append(dict(kwargs))
            if len(self.calls) == 1:
                raise RuntimeError(
                    "Unsupported parameter: 'max_tokens' is not supported with this model. "
                    "Use 'max_completion_tokens' instead."
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))],
                model="gpt-5.4-mini",
            )

    completions = FakeCompletions()
    service = AzureOpenAILLMService(
        api_key="key",
        azure_endpoint="https://example.openai.azure.com/",
        api_version="2025-04-01-preview",
        models={"fast": "gpt-5.4-mini"},
        timeout=15,
    )
    service._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service._connected = True

    import asyncio

    result = asyncio.run(service.generate("ping", mode="fast"))

    assert result.content == "pong"
    assert len(completions.calls) == 2
    assert completions.calls[0]["max_tokens"] == 1200
    assert "max_completion_tokens" not in completions.calls[0]
    assert completions.calls[1]["max_completion_tokens"] == 1200
    assert "max_tokens" not in completions.calls[1]
