import pytest

from ai_factory.openai_provider import OpenAIProvider


def test_openai_provider_requires_model(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    with pytest.raises(
        ValueError,
        match="OpenAI model must be configured",
    ):
        OpenAIProvider(
            model="",
        )


def test_openai_provider_requires_api_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY",
    ):
        OpenAIProvider(
            model="test-model",
        )


def test_openai_provider_stores_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "temperature": 0.2,
            "max_output_tokens": 2000,
        },
    )

    assert provider.model == "test-model"
    assert provider.api_key == "test-key"
    assert provider.settings["temperature"] == 0.2
    assert provider.settings["max_output_tokens"] == 2000


def test_openai_provider_run_builds_prompt_and_executes(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    captured = {}

    def fake_execute(prompt: str) -> str:
        captured["prompt"] = prompt
        return "model-output"

    monkeypatch.setattr(
        provider,
        "_execute",
        fake_execute,
    )

    context = {
        "agent_name": "architect",
        "contract": "Architect contract",
        "project": {
            "project": {
                "name": "Test Project",
            }
        },
        "state": {
            "agents": {
                "architect": {
                    "status": "READY",
                }
            }
        },
        "artifacts": {},
    }

    result = provider.run(context)

    assert result == "model-output"
    assert "Agent: architect" in captured["prompt"]
    assert "Architect contract" in captured["prompt"]
    assert "Test Project" in captured["prompt"]
