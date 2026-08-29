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

    monkeypatch.setattr(
        "ai_factory.openai_provider.load_dotenv",
        lambda *args, **kwargs: False,
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


def test_openai_provider_execute_uses_responses_api(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 2000,
        },
    )

    captured = {}

    class FakeResponse:
        output_text = "generated-agent-output"

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    result = provider._execute(
        "prepared agent prompt"
    )

    assert result == "generated-agent-output"
    assert captured["model"] == "test-model"
    assert captured["input"] == "prepared agent prompt"
    assert captured["max_output_tokens"] == 2000
