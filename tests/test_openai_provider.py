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

        return """
{
  "status": "COMPLETED",
  "summary": "Model execution completed.",
  "artifacts": [],
  "questions": [],
  "blockers": [],
  "handoff": null,
  "metadata": {}
}
"""

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

    assert result.status == "COMPLETED"
    assert result.summary == "Model execution completed."
    assert result.artifacts == []
    assert "Agent: architect" in captured["prompt"]
    assert "Architect contract" in captured["prompt"]
    assert "Test Project" in captured["prompt"]
    assert "## Required Output Format" in captured["prompt"]
    assert '"artifact_requests"' in captured["prompt"]
    assert "Artifact policy:" in captured["prompt"]
    assert "Do NOT generate large document contents inside this response." in (
        captured["prompt"]
    )
    assert (
        "Use artifact_requests to declare documents or files that should "
        "be generated separately by the Factory."
        in captured["prompt"]
    )


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
        status = "completed"
        incomplete_details = None
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
    assert "text" in captured
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["name"] == "agent_result"
    assert captured["text"]["format"]["strict"] is True

    schema = captured["text"]["format"]["schema"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert "status" in schema["properties"]
    assert "summary" in schema["properties"]
    assert "artifacts" in schema["properties"]
    assert "artifact_requests" in schema["properties"]
    assert "questions" in schema["properties"]
    assert "blockers" in schema["properties"]
    assert "handoff" in schema["properties"]
    assert "metadata" in schema["properties"]
    assert "artifact_requests" in schema["required"]

    assert set(schema["required"]) == {
        "status",
        "summary",
        "artifacts",
        "artifact_requests",
        "questions",
        "blockers",
        "handoff",
        "metadata",
    }


def test_openai_provider_parses_structured_agent_result(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    raw_output = """
{
  "status": "COMPLETED",
  "summary": "Architecture proposal completed.",
  "artifacts": [],
  "artifact_requests": [
    {
      "path": "knowledge/architecture/system.md",
      "purpose": "Document the approved system architecture."
    }
  ],
  "questions": [],
  "blockers": [],
  "handoff": "developer",
  "metadata": {
    "confidence": "high"
  }
}
"""

    result = provider._parse_result(raw_output)

    assert result.status == "COMPLETED"
    assert result.summary == "Architecture proposal completed."
    assert result.artifacts == []
    assert len(result.artifact_requests) == 1
    assert (
        result.artifact_requests[0].path
        == "knowledge/architecture/system.md"
    )
    assert (
        result.artifact_requests[0].purpose
        == "Document the approved system architecture."
    )
    assert result.questions == []
    assert result.blockers == []
    assert result.handoff == "developer"
    assert result.metadata["confidence"] == "high"


def test_openai_provider_rejects_invalid_json(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    with pytest.raises(
        ValueError,
        match="invalid structured agent result",
    ):
        provider._parse_result(
            "not-json"
        )


def test_openai_provider_rejects_artifact_without_path(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    raw_output = """
{
  "status": "COMPLETED",
  "summary": "Done.",
  "artifacts": [
    {
      "content": "Missing path"
    }
  ],
  "questions": [],
  "blockers": [],
  "handoff": null,
  "metadata": {}
}
"""

    with pytest.raises(
        ValueError,
        match="artifact path is required",
    ):
        provider._parse_result(raw_output)


def test_openai_provider_rejects_incomplete_response(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeIncompleteDetails:
        reason = "max_output_tokens"

        def __repr__(self) -> str:
            return "FakeIncompleteDetails(reason='max_output_tokens')"

    class FakeResponse:
        status = "incomplete"
        incomplete_details = FakeIncompleteDetails()
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="OpenAI response was incomplete",
    ):
        provider._execute(
            "prepared prompt"
        )


def test_openai_provider_rejects_empty_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="returned no text output",
    ):
        provider._execute(
            "prepared prompt"
        )


def test_openai_provider_rejects_artifact_request_without_purpose(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    raw_output = """
{
  "status": "COMPLETED",
  "summary": "Done.",
  "artifacts": [],
  "artifact_requests": [
    {
      "path": "knowledge/product/requirements.md"
    }
  ],
  "questions": [],
  "blockers": [],
  "handoff": null,
  "metadata": {}
}
"""

    with pytest.raises(
        ValueError,
        match="artifact request purpose is required",
    ):
        provider._parse_result(raw_output)


def test_openai_provider_generate_returns_artifact_content(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 1500,
        },
    )

    captured = {}

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = "  # Generated Artifact\n\nContent.  "

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    result = provider.generate(
        "artifact prompt"
    )

    assert result == "# Generated Artifact\n\nContent."
    assert captured["model"] == "test-model"
    assert captured["input"] == "artifact prompt"
    assert captured["max_output_tokens"] == 1500
    assert "text" not in captured


def test_openai_provider_generate_rejects_incomplete_response(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeIncompleteDetails:
        reason = "max_output_tokens"

        def __repr__(self) -> str:
            return "FakeIncompleteDetails(reason='max_output_tokens')"

    class FakeResponse:
        status = "incomplete"
        incomplete_details = FakeIncompleteDetails()
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="artifact response was incomplete",
    ):
        provider.generate(
            "artifact prompt"
        )


def test_openai_provider_generate_rejects_empty_content(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="no artifact content",
    ):
        provider.generate(
            "artifact prompt"
        )
