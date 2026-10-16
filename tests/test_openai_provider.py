import pytest

from ai_factory.openai_provider import (
    OpenAIProvider,
    build_devops_result_schema,
    build_implementation_result_schema,
    build_qa_result_schema,
    build_sre_result_schema,
    build_security_result_schema,
)


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
    assert "implementation_requests" in schema["properties"]
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
        "implementation_requests",
        "questions",
        "question_details",
        "owner_summary",
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


def test_openai_provider_execute_handles_rate_limit(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeRateLimitError(Exception):
        pass

    monkeypatch.setattr(
        "ai_factory.openai_provider.RateLimitError",
        FakeRateLimitError,
    )

    class FakeResponses:
        def create(self, **kwargs):
            raise FakeRateLimitError(
                "rate limit exceeded"
            )

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="OpenAI rate limit exceeded",
    ):
        provider._execute(
            "prepared prompt"
        )


def test_openai_provider_generate_handles_rate_limit(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeRateLimitError(Exception):
        pass

    monkeypatch.setattr(
        "ai_factory.openai_provider.RateLimitError",
        FakeRateLimitError,
    )

    class FakeResponses:
        def create(self, **kwargs):
            raise FakeRateLimitError(
                "rate limit exceeded"
            )

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="OpenAI rate limit exceeded",
    ):
        provider.generate(
            "artifact prompt"
        )


def test_parse_result_supports_implementation_requests(
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
        "summary": "Implementation planning completed.",
        "artifacts": [],
        "artifact_requests": [],
        "implementation_requests": [
            {
                "id": "US-001",
                "title": "Passenger authentication",
                "purpose": "Implement authentication with automated tests.",
                "kind": "IMPLEMENTATION",
                "scope": "TASK",
                "verification": {
                    "allow_full_suite": false,
                    "baseline_required": true
                }
            },
            {
                "id": "US-002",
                "title": "Ride request workflow",
                "purpose": "Implement ride creation and status handling.",
                "kind": "IMPLEMENTATION",
                "scope": "TASK",
                "verification": {
                    "allow_full_suite": false,
                    "baseline_required": true
                }
            }
        ],
        "questions": [],
        "blockers": [],
        "handoff": null,
        "metadata": {
            "technology_proposal": {
                "components": []
            }
        }
    }
    """

    result = provider._parse_result(
        raw_output
    )

    assert len(result.implementation_requests) == 2

    first = result.implementation_requests[0]

    assert first.id == "US-001"
    assert first.title == "Passenger authentication"
    assert (
        first.purpose
        == "Implement authentication with automated tests."
    )

    second = result.implementation_requests[1]

    assert second.id == "US-002"
    assert second.title == "Ride request workflow"


def test_build_implementation_result_schema() -> None:
    schema = build_implementation_result_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert set(schema["required"]) == {
        "task_id",
        "summary",
        "files",
        "setup_commands",
        "tests",
        "blockers",
    }

    properties = schema["properties"]

    assert "task_id" in properties
    assert "summary" in properties
    assert "files" in properties
    assert "setup_commands" in properties
    assert "tests" in properties
    assert "blockers" in properties

    file_schema = properties["files"]["items"]

    assert file_schema["type"] == "object"
    assert file_schema["additionalProperties"] is False

    assert set(file_schema["required"]) == {
        "path",
        "content",
        "operation",
    }

    assert file_schema["properties"]["operation"]["enum"] == [
        "write"
    ]


def test_build_qa_result_schema() -> None:
    schema = build_qa_result_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert set(schema["required"]) == {
        "summary",
        "passed",
        "defects",
        "test_commands",
        "blockers",
    }

    properties = schema["properties"]

    assert "summary" in properties
    assert "passed" in properties
    assert "defects" in properties
    assert "test_commands" in properties
    assert "blockers" in properties

    defect_schema = properties["defects"]["items"]

    assert defect_schema["type"] == "object"
    assert defect_schema["additionalProperties"] is False

    assert set(defect_schema["required"]) == {
        "id",
        "title",
        "severity",
        "related_story",
        "expected",
        "actual",
    }

    assert defect_schema["properties"]["severity"]["enum"] == [
        "Critical",
        "High",
        "Medium",
        "Low",
    ]


def test_build_security_result_schema() -> None:
    schema = build_security_result_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert set(schema["required"]) == {
        "summary",
        "passed",
        "findings",
        "test_commands",
        "blockers",
    }

    properties = schema["properties"]

    assert "summary" in properties
    assert "passed" in properties
    assert "findings" in properties
    assert "test_commands" in properties
    assert "blockers" in properties

    finding_schema = properties["findings"]["items"]

    assert finding_schema["type"] == "object"
    assert finding_schema["additionalProperties"] is False

    assert set(finding_schema["required"]) == {
        "id",
        "title",
        "severity",
        "affected_component",
        "description",
        "impact",
        "evidence",
        "recommended_remediation",
        "priority",
        "status",
    }

    assert finding_schema["properties"]["severity"]["enum"] == [
        "Critical",
        "High",
        "Medium",
        "Low",
        "Informational",
    ]


def test_build_sre_result_schema() -> None:
    schema = build_sre_result_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert set(schema["required"]) == {
        "summary",
        "passed",
        "findings",
        "test_commands",
        "blockers",
        "observability_ready",
        "incident_readiness",
    }

    properties = schema["properties"]

    assert "summary" in properties
    assert "passed" in properties
    assert "findings" in properties
    assert "test_commands" in properties
    assert "blockers" in properties
    assert "observability_ready" in properties
    assert "incident_readiness" in properties

    finding_schema = properties["findings"]["items"]

    assert finding_schema["type"] == "object"
    assert finding_schema["additionalProperties"] is False

    assert set(finding_schema["required"]) == {
        "id",
        "title",
        "severity",
        "category",
        "description",
        "recommendation",
        "status",
    }

    assert finding_schema["properties"]["severity"]["enum"] == [
        "Critical",
        "High",
        "Medium",
        "Low",
        "Informational",
    ]


def test_build_devops_result_schema() -> None:
    schema = build_devops_result_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False

    assert set(schema["required"]) == {
        "summary",
        "passed",
        "changes",
        "test_commands",
        "blockers",
        "deployment_ready",
        "rollback_strategy",
    }

    properties = schema["properties"]

    assert "summary" in properties
    assert "passed" in properties
    assert "changes" in properties
    assert "test_commands" in properties
    assert "blockers" in properties
    assert "deployment_ready" in properties
    assert "rollback_strategy" in properties

    change_schema = properties["changes"]["items"]

    assert change_schema["type"] == "object"
    assert change_schema["additionalProperties"] is False

    assert set(change_schema["required"]) == {
        "path",
        "description",
        "category",
    }


def test_parse_devops_result(
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
        "summary": "DevOps automation completed.",
        "passed": true,
        "changes": [
            {
                "path": ".github/workflows/ci.yml",
                "description": "Add CI pipeline.",
                "category": "ci_cd"
            }
        ],
        "test_commands": [
            "python -m pytest -q"
        ],
        "blockers": [],
        "deployment_ready": true,
        "rollback_strategy": "Redeploy the previous stable release."
    }
    """

    result = provider._parse_devops_result(
        raw_output
    )

    assert result.summary == (
        "DevOps automation completed."
    )

    assert result.passed is True
    assert len(result.changes) == 1

    change = result.changes[0]

    assert change.path == ".github/workflows/ci.yml"
    assert change.description == "Add CI pipeline."
    assert change.category == "ci_cd"

    assert result.test_commands == [
        "python -m pytest -q"
    ]

    assert result.blockers == []
    assert result.deployment_ready is True

    assert result.rollback_strategy == (
        "Redeploy the previous stable release."
    )


def test_parse_devops_result_rejects_invalid_json(
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
        match="invalid DevOps JSON",
    ):
        provider._parse_devops_result(
            "not-json"
        )


def test_parse_devops_result_rejects_invalid_deployment_ready(
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
        "summary": "DevOps automation completed.",
        "passed": true,
        "changes": [],
        "test_commands": [],
        "blockers": [],
        "deployment_ready": "yes",
        "rollback_strategy": "Rollback."
    }
    """

    with pytest.raises(
        ValueError,
        match="deployment_ready must be a boolean",
    ):
        provider._parse_devops_result(
            raw_output
        )


def test_parse_sre_result(
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
        "summary": "SRE validation completed.",
        "passed": true,
        "findings": [
            {
                "id": "SRE-001",
                "title": "Missing health check",
                "severity": "High",
                "category": "health_check",
                "description": "The service exposes no health endpoint.",
                "recommendation": "Add a health endpoint.",
                "status": "OPEN"
            }
        ],
        "test_commands": [
            "python -m pytest -q"
        ],
        "blockers": [],
        "observability_ready": true,
        "incident_readiness": true
    }
    """

    result = provider._parse_sre_result(
        raw_output
    )

    assert result.summary == (
        "SRE validation completed."
    )

    assert result.passed is True
    assert len(result.findings) == 1

    finding = result.findings[0]

    assert finding.id == "SRE-001"
    assert finding.title == "Missing health check"
    assert finding.severity == "High"
    assert finding.category == "health_check"
    assert finding.description == (
        "The service exposes no health endpoint."
    )
    assert finding.recommendation == (
        "Add a health endpoint."
    )
    assert finding.status == "OPEN"

    assert result.test_commands == [
        "python -m pytest -q"
    ]

    assert result.blockers == []
    assert result.observability_ready is True
    assert result.incident_readiness is True


def test_parse_sre_result_rejects_invalid_json(
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
        match="invalid SRE JSON",
    ):
        provider._parse_sre_result(
            "not-json"
        )


def test_parse_sre_result_rejects_invalid_severity(
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
        "summary": "SRE validation completed.",
        "passed": false,
        "findings": [
            {
                "id": "SRE-001",
                "title": "Reliability issue",
                "severity": "Extreme",
                "category": "reliability",
                "description": "Invalid reliability state.",
                "recommendation": "Fix reliability controls.",
                "status": "OPEN"
            }
        ],
        "test_commands": [],
        "blockers": [],
        "observability_ready": false,
        "incident_readiness": false
    }
    """

    with pytest.raises(
        ValueError,
        match="Invalid SRE finding severity",
    ):
        provider._parse_sre_result(
            raw_output
        )


def test_parse_sre_result_rejects_invalid_observability_ready(
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
        "summary": "SRE validation completed.",
        "passed": true,
        "findings": [],
        "test_commands": [],
        "blockers": [],
        "observability_ready": "yes",
        "incident_readiness": true
    }
    """

    with pytest.raises(
        ValueError,
        match="observability_ready must be a boolean",
    ):
        provider._parse_sre_result(
            raw_output
        )


def test_validate_sre_uses_structured_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    captured_kwargs = {}

    class FakeResponse:
        status = "completed"
        output_text = """
        {
            "summary": "SRE validation completed.",
            "passed": true,
            "findings": [
                {
                    "id": "SRE-001",
                    "title": "Missing health check",
                    "severity": "High",
                    "category": "health_check",
                    "description": "The service exposes no health endpoint.",
                    "recommendation": "Add a health endpoint.",
                    "status": "OPEN"
                }
            ],
            "test_commands": [
                "python -m pytest -q"
            ],
            "blockers": [],
            "observability_ready": true,
            "incident_readiness": true
        }
        """

    def fake_create(**kwargs):
        captured_kwargs.update(
            kwargs
        )
        return FakeResponse()

    monkeypatch.setattr(
        provider.client.responses,
        "create",
        fake_create,
    )

    result = provider.validate_sre(
        "Validate reliability and observability."
    )

    assert captured_kwargs["model"] == "test-model"

    assert captured_kwargs["input"] == (
        "Validate reliability and observability."
    )

    output_format = (
        captured_kwargs["text"]["format"]
    )

    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "sre_result"
    assert output_format["strict"] is True

    assert (
        output_format["schema"]
        == build_sre_result_schema()
    )

    assert result.summary == (
        "SRE validation completed."
    )

    assert result.passed is True
    assert len(result.findings) == 1

    assert result.findings[0].id == "SRE-001"
    assert result.findings[0].severity == "High"

    assert result.test_commands == [
        "python -m pytest -q"
    ]

    assert result.blockers == []
    assert result.observability_ready is True
    assert result.incident_readiness is True


def test_validate_devops_uses_structured_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    captured_kwargs = {}

    class FakeResponse:
        status = "completed"
        output_text = """
        {
            "summary": "DevOps automation completed.",
            "passed": true,
            "changes": [
                {
                    "path": ".github/workflows/ci.yml",
                    "description": "Add CI pipeline.",
                    "category": "ci_cd"
                }
            ],
            "test_commands": [
                "python -m pytest -q"
            ],
            "blockers": [],
            "deployment_ready": true,
            "rollback_strategy": "Redeploy the previous stable release."
        }
        """

    def fake_create(**kwargs):
        captured_kwargs.update(
            kwargs
        )
        return FakeResponse()

    monkeypatch.setattr(
        provider.client.responses,
        "create",
        fake_create,
    )

    result = provider.validate_devops(
        "Validate DevOps automation."
    )

    assert captured_kwargs["model"] == "test-model"
    assert captured_kwargs["input"] == (
        "Validate DevOps automation."
    )

    output_format = (
        captured_kwargs["text"]["format"]
    )

    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "devops_result"
    assert output_format["strict"] is True

    assert (
        output_format["schema"]
        == build_devops_result_schema()
    )

    assert result.summary == (
        "DevOps automation completed."
    )
    assert result.passed is True
    assert len(result.changes) == 1
    assert result.changes[0].path == (
        ".github/workflows/ci.yml"
    )
    assert result.test_commands == [
        "python -m pytest -q"
    ]
    assert result.blockers == []
    assert result.deployment_ready is True


def test_parse_security_result(
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
        "summary": "Security validation completed.",
        "passed": false,
        "findings": [
            {
                "id": "SEC-001",
                "title": "Hard-coded secret detected",
                "severity": "High",
                "affected_component": "backend",
                "description": "A secret is committed in source code.",
                "impact": "Credential exposure.",
                "evidence": "src/config.py",
                "recommended_remediation": "Move the secret to environment variables.",
                "priority": "P1",
                "status": "OPEN"
            }
        ],
        "test_commands": [
            "python -m pytest tests/test_security.py -q"
        ],
        "blockers": []
    }
    """

    result = provider._parse_security_result(
        raw_output
    )

    assert result.summary == (
        "Security validation completed."
    )
    assert result.passed is False

    assert len(result.findings) == 1

    finding = result.findings[0]

    assert finding.id == "SEC-001"
    assert finding.title == (
        "Hard-coded secret detected"
    )
    assert finding.severity == "High"
    assert finding.affected_component == "backend"
    assert finding.description == (
        "A secret is committed in source code."
    )
    assert finding.impact == "Credential exposure."
    assert finding.evidence == "src/config.py"
    assert finding.recommended_remediation == (
        "Move the secret to environment variables."
    )
    assert finding.priority == "P1"
    assert finding.status == "OPEN"

    assert result.test_commands == [
        "python -m pytest tests/test_security.py -q"
    ]
    assert result.blockers == []


def test_parse_security_result_rejects_invalid_json(
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
        match="invalid security JSON",
    ):
        provider._parse_security_result(
            "not-json"
        )


def test_parse_security_result_rejects_invalid_severity(
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
        "summary": "Security validation completed.",
        "passed": false,
        "findings": [
            {
                "id": "SEC-001",
                "title": "Security issue",
                "severity": "Extreme",
                "affected_component": "backend",
                "description": "Invalid security configuration.",
                "impact": "Potential compromise.",
                "evidence": "src/config.py",
                "recommended_remediation": "Fix configuration.",
                "priority": "P1",
                "status": "OPEN"
            }
        ],
        "test_commands": [],
        "blockers": []
    }
    """

    with pytest.raises(
        ValueError,
        match="Invalid security finding severity",
    ):
        provider._parse_security_result(
            raw_output
        )


def test_validate_security_uses_structured_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    captured_kwargs = {}

    class FakeResponse:
        status = "completed"
        output_text = """
        {
            "summary": "Security validation completed.",
            "passed": true,
            "findings": [],
            "test_commands": [
                "python -m pytest tests/test_security.py -q"
            ],
            "blockers": []
        }
        """

    def fake_create(**kwargs):
        captured_kwargs.update(
            kwargs
        )
        return FakeResponse()

    monkeypatch.setattr(
        provider.client.responses,
        "create",
        fake_create,
    )

    result = provider.validate_security(
        "Validate application security."
    )

    assert captured_kwargs["model"] == "test-model"
    assert captured_kwargs["input"] == (
        "Validate application security."
    )

    output_format = (
        captured_kwargs["text"]["format"]
    )

    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "security_result"
    assert output_format["strict"] is True

    assert (
        output_format["schema"]
        == build_security_result_schema()
    )

    assert result.summary == (
        "Security validation completed."
    )
    assert result.passed is True
    assert result.findings == []
    assert result.test_commands == [
        "python -m pytest tests/test_security.py -q"
    ]
    assert result.blockers == []


def test_parse_qa_result(
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
        "summary": "QA validation completed.",
        "passed": false,
        "defects": [
            {
                "id": "QA-001",
                "title": "Invalid credentials return 500",
                "severity": "High",
                "related_story": "US-001",
                "expected": "401 response",
                "actual": "500 response"
            }
        ],
        "test_commands": [
            "python -m pytest tests/test_auth.py -q"
        ],
        "blockers": []
    }
    """

    result = provider._parse_qa_result(
        raw_output
    )

    assert result.summary == "QA validation completed."
    assert result.passed is False

    assert len(result.defects) == 1

    defect = result.defects[0]

    assert defect.id == "QA-001"
    assert defect.title == "Invalid credentials return 500"
    assert defect.severity == "High"
    assert defect.related_story == "US-001"
    assert defect.expected == "401 response"
    assert defect.actual == "500 response"

    assert result.test_commands == [
        "python -m pytest tests/test_auth.py -q"
    ]

    assert result.blockers == []


def test_parse_qa_result_rejects_invalid_json(
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
        match="invalid QA JSON",
    ):
        provider._parse_qa_result(
            "not-json"
        )


def test_parse_qa_result_rejects_invalid_severity(
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
        "summary": "QA validation completed.",
        "passed": false,
        "defects": [
            {
                "id": "QA-001",
                "title": "Broken behavior",
                "severity": "Extreme",
                "related_story": "US-001",
                "expected": "Expected behavior",
                "actual": "Actual behavior"
            }
        ],
        "test_commands": [],
        "blockers": []
    }
    """

    with pytest.raises(
        ValueError,
        match="Invalid QA defect severity",
    ):
        provider._parse_qa_result(
            raw_output
        )


def test_validate_qa_uses_structured_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    captured_kwargs = {}

    class FakeResponse:
        status = "completed"
        output_text = """
        {
            "summary": "QA validation completed.",
            "passed": true,
            "defects": [],
            "test_commands": [
                "python -m pytest -q"
            ],
            "blockers": []
        }
        """

    def fake_create(**kwargs):
        captured_kwargs.update(
            kwargs
        )
        return FakeResponse()

    monkeypatch.setattr(
        provider.client.responses,
        "create",
        fake_create,
    )

    result = provider.validate_qa(
        "Validate the application."
    )

    assert captured_kwargs["model"] == "test-model"
    assert captured_kwargs["input"] == (
        "Validate the application."
    )

    output_format = (
        captured_kwargs["text"]["format"]
    )

    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "qa_result"
    assert output_format["strict"] is True

    assert (
        output_format["schema"]
        == build_qa_result_schema()
    )

    assert result.summary == (
        "QA validation completed."
    )
    assert result.passed is True
    assert result.defects == []
    assert result.test_commands == [
        "python -m pytest -q"
    ]
    assert result.blockers == []


def test_parse_implementation_result(
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
        "task_id": "US-001",
        "summary": "Passenger authentication implemented.",
        "files": [
            {
                "path": "src/accounts/models.py",
                "content": "# models",
                "operation": "write"
            },
            {
                "path": "tests/test_auth.py",
                "content": "# tests",
                "operation": "write"
            }
        ],
        "tests": [
            "pytest tests/test_auth.py"
        ],
        "blockers": []
    }
    """

    result = provider._parse_implementation_result(
        raw_output
    )

    assert result.task_id == "US-001"
    assert (
        result.summary
        == "Passenger authentication implemented."
    )

    assert len(result.files) == 2

    assert result.files[0].path == "src/accounts/models.py"
    assert result.files[0].content == "# models"
    assert result.files[0].operation == "write"

    assert result.files[1].path == "tests/test_auth.py"

    assert result.tests == [
        "pytest tests/test_auth.py"
    ]

    assert result.blockers == []


def test_parse_implementation_result_rejects_invalid_json(
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
        match="invalid implementation JSON",
    ):
        provider._parse_implementation_result(
            "not-json"
        )


def test_parse_implementation_result_rejects_unsupported_operation(
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
        "task_id": "US-001",
        "summary": "Unsafe change.",
        "files": [
            {
                "path": "src/app.py",
                "content": "",
                "operation": "delete"
            }
        ],
        "tests": [],
        "blockers": []
    }
    """

    with pytest.raises(
        ValueError,
        match="Unsupported implementation operation",
    ):
        provider._parse_implementation_result(
            raw_output
        )


def test_openai_provider_implement_returns_structured_result(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 2500,
        },
    )

    captured = {}

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
        {
            "task_id": "US-001",
            "summary": "Authentication implemented.",
            "files": [
                {
                    "path": "src/accounts/models.py",
                    "content": "# models",
                    "operation": "write"
                }
            ],
            "tests": [
                "pytest tests/test_auth.py"
            ],
            "blockers": []
        }
        """

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    result = provider.implement(
        "implementation prompt"
    )

    assert result.task_id == "US-001"
    assert result.summary == "Authentication implemented."
    assert len(result.files) == 1
    assert result.files[0].path == "src/accounts/models.py"

    assert captured["model"] == "test-model"
    assert captured["input"] == "implementation prompt"
    # A shared budget sized for summaries is raised to the implementation
    # floor rather than truncating generated files.
    assert captured["max_output_tokens"] == 32000

    response_format = captured["text"]["format"]

    assert response_format["type"] == "json_schema"
    assert response_format["name"] == "implementation_result"
    assert response_format["strict"] is True


def test_openai_provider_implement_rejects_incomplete_response(
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
        status = "incomplete"
        incomplete_details = "max_output_tokens"
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="implementation response was incomplete",
    ):
        provider.implement(
            "implementation prompt"
        )


def test_openai_provider_implement_retries_once_when_output_token_limit_is_reached(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "implementation_max_output_tokens": 5000,
            "implementation_retry_max_output_tokens": 10000,
        },
    )

    calls = []

    class FakeIncompleteDetails:
        reason = "max_output_tokens"

    class FakeIncompleteResponse:
        status = "incomplete"
        incomplete_details = FakeIncompleteDetails()
        output_text = ""

    class FakeCompletedResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
        {
          "task_id": "TASK-001",
          "summary": "Implementation completed after retry.",
          "files": [],
          "setup_commands": [],
          "tests": [],
          "blockers": []
        }
        """

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)

            if len(calls) == 1:
                return FakeIncompleteResponse()

            return FakeCompletedResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    result = provider.implement(
        "implementation prompt"
    )

    assert result.task_id == "TASK-001"
    assert len(calls) == 2
    assert calls[0]["max_output_tokens"] == 5000
    assert calls[1]["max_output_tokens"] == 10000
    assert calls[0]["input"] == calls[1]["input"]


def test_openai_provider_implement_retries_output_limit_only_once(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "implementation_max_output_tokens": 5000,
            "implementation_retry_max_output_tokens": 10000,
        },
    )

    calls = []

    class FakeIncompleteDetails:
        reason = "max_output_tokens"

    class FakeResponse:
        status = "incomplete"
        incomplete_details = FakeIncompleteDetails()
        output_text = ""

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="implementation response was incomplete",
    ):
        provider.implement(
            "implementation prompt"
        )

    assert len(calls) == 2
    assert calls[0]["max_output_tokens"] == 5000
    assert calls[1]["max_output_tokens"] == 10000


def test_openai_provider_implementation_schema_requires_setup_commands(
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

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
        {
          "task_id": "TASK-001",
          "summary": "Done.",
          "files": [],
          "setup_commands": [],
          "tests": [],
          "blockers": []
        }
        """

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    provider.implement("implementation prompt")

    schema = captured["text"]["format"]["schema"]

    assert "setup_commands" in schema["properties"]
    assert "setup_commands" in schema["required"]


def test_openai_provider_rejects_invalid_implementation_setup_commands(
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
        match="setup_commands must be a list of strings",
    ):
        provider._parse_implementation_result(
            """
            {
              "task_id": "TASK-001",
              "summary": "Foundation generated.",
              "files": [],
              "setup_commands": "npm install --ignore-scripts",
              "tests": [],
              "blockers": []
            }
            """
        )


def test_openai_provider_parses_implementation_setup_commands(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    result = provider._parse_implementation_result(
        """
        {
          "task_id": "TASK-001",
          "summary": "Foundation generated.",
          "files": [],
          "setup_commands": [
            "npm install --ignore-scripts"
          ],
          "tests": [
            "npm test"
          ],
          "blockers": []
        }
        """
    )

    assert result.setup_commands == [
        "npm install --ignore-scripts"
    ]


def test_openai_provider_run_prompt_includes_implementation_requests(
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
  "summary": "Product discovery completed.",
  "artifacts": [],
  "artifact_requests": [],
  "implementation_requests": [],
  "questions": [],
  "blockers": [],
  "handoff": null,
  "metadata": {
    "technology_proposal": null
  }
}
"""

    monkeypatch.setattr(
        provider,
        "_execute",
        fake_execute,
    )

    provider.run(
        {
            "agent_name": "product",
            "contract": "Product contract",
            "project": {},
            "state": {},
            "artifacts": {},
        }
    )

    assert (
        '"implementation_requests": ['
        in captured["prompt"]
    )


def test_openai_provider_agent_schema_allows_null_technology_proposal(
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

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
{
  "status": "COMPLETED",
  "summary": "Completed.",
  "artifacts": [],
  "artifact_requests": [],
  "implementation_requests": [],
  "questions": [],
  "blockers": [],
  "handoff": null,
  "metadata": {
    "technology_proposal": null
  }
}
"""

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    provider._execute(
        "prepared prompt"
    )

    schema = captured[
        "text"
    ]["format"]["schema"]

    technology_proposal_schema = schema[
        "properties"
    ]["metadata"]["properties"][
        "technology_proposal"
    ]

    assert "null" in technology_proposal_schema["type"]


def test_openai_provider_execute_prefers_agent_max_output_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 8000,
            "agent_max_output_tokens": 2000,
        },
    )

    captured = {}

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
        {
          "status": "COMPLETED",
          "summary": "Done.",
          "artifacts": [],
          "artifact_requests": [],
          "implementation_requests": [],
          "questions": [],
          "blockers": [],
          "handoff": null,
          "metadata": {
            "technology_proposal": null
          }
        }
        """

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    provider._execute("agent prompt")

    assert captured["max_output_tokens"] == 2000


def test_openai_provider_generate_prefers_artifact_max_output_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 8000,
            "artifact_max_output_tokens": 3000,
        },
    )

    captured = {}

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = "# Generated Artifact\n\nContent."

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    provider.generate("artifact prompt")

    assert captured["max_output_tokens"] == 3000


def test_openai_provider_implement_prefers_implementation_max_output_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "max_output_tokens": 8000,
            "implementation_max_output_tokens": 5000,
        },
    )

    captured = {}

    class FakeResponse:
        status = "completed"
        incomplete_details = None
        output_text = """
        {
          "task_id": "TASK-001",
          "summary": "Implementation completed.",
          "files": [],
          "tests": [],
          "blockers": []
        }
        """

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    provider.implement("implementation prompt")

    assert captured["max_output_tokens"] == 5000


def test_openai_provider_implement_handles_rate_limit(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
    )

    class FakeRateLimitError(Exception):
        pass

    monkeypatch.setattr(
        "ai_factory.openai_provider.RateLimitError",
        FakeRateLimitError,
    )

    class FakeResponses:
        def create(self, **kwargs):
            raise FakeRateLimitError(
                "rate limit exceeded"
            )

    class FakeClient:
        responses = FakeResponses()

    provider.client = FakeClient()

    with pytest.raises(
        ValueError,
        match="OpenAI rate limit exceeded",
    ):
        provider.implement(
            "implementation prompt"
        )


def capture_openai_client(
    monkeypatch,
) -> dict:
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "ai_factory.openai_provider.OpenAI",
        FakeOpenAI,
    )

    return captured


def test_openai_provider_defaults_client_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    captured = capture_openai_client(monkeypatch)

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "base_url": None,
            "api_key_env": None,
        },
    )

    assert captured == {
        "api_key": "test-key",
    }
    assert provider.api_key_env == "OPENAI_API_KEY"
    assert provider.base_url is None


def test_openai_provider_passes_base_url_to_client(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    captured = capture_openai_client(monkeypatch)

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "base_url": "http://localhost:11434/v1",
        },
    )

    assert captured == {
        "api_key": "test-key",
        "base_url": "http://localhost:11434/v1",
    }
    assert provider.base_url == "http://localhost:11434/v1"


def test_openai_provider_reads_key_from_configured_env(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )
    monkeypatch.setenv(
        "CUSTOM_LLM_KEY",
        "custom-key",
    )

    captured = capture_openai_client(monkeypatch)

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "api_key_env": "CUSTOM_LLM_KEY",
        },
    )

    assert captured["api_key"] == "custom-key"
    assert provider.api_key == "custom-key"
    assert provider.api_key_env == "CUSTOM_LLM_KEY"


def test_openai_provider_names_missing_configured_key_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "ignored-key",
    )
    monkeypatch.delenv(
        "CUSTOM_LLM_KEY",
        raising=False,
    )

    monkeypatch.setattr(
        "ai_factory.openai_provider.load_dotenv",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(
        ValueError,
        match="CUSTOM_LLM_KEY environment variable is required",
    ):
        OpenAIProvider(
            model="test-model",
            settings={
                "api_key_env": "CUSTOM_LLM_KEY",
            },
        )


@pytest.mark.parametrize(
    "settings, message",
    [
        ({"api_key_env": ""}, "api_key_env"),
        ({"api_key_env": 42}, "api_key_env"),
        ({"base_url": "  "}, "base_url"),
        ({"base_url": 8080}, "base_url"),
    ],
)
def test_openai_provider_rejects_invalid_client_settings(
    monkeypatch,
    settings,
    message,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    capture_openai_client(monkeypatch)

    with pytest.raises(
        ValueError,
        match=message,
    ):
        OpenAIProvider(
            model="test-model",
            settings=settings,
        )


def _implementation_budget_provider(monkeypatch, settings):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    return OpenAIProvider(
        model="test-model",
        settings=settings,
    )


def test_implementation_budget_honors_an_explicit_setting(monkeypatch) -> None:
    provider = _implementation_budget_provider(
        monkeypatch,
        {
            "max_output_tokens": 2500,
            "implementation_max_output_tokens": 8000,
            "implementation_retry_max_output_tokens": 9000,
        },
    )

    assert provider._implementation_max_output_tokens() == 8000
    assert provider._implementation_retry_max_output_tokens() == 9000


def test_implementation_budget_keeps_a_larger_shared_budget(monkeypatch) -> None:
    provider = _implementation_budget_provider(
        monkeypatch,
        {"max_output_tokens": 50000},
    )

    assert provider._implementation_max_output_tokens() == 50000
    assert provider._implementation_retry_max_output_tokens() == 100000


def test_implementation_budget_stays_unset_without_any_budget(monkeypatch) -> None:
    provider = _implementation_budget_provider(
        monkeypatch,
        {"max_output_tokens": None},
    )

    assert provider._implementation_max_output_tokens() is None
    assert provider._implementation_retry_max_output_tokens() is None


def test_implementation_budget_retries_truncation_with_double_budget(
    monkeypatch,
) -> None:
    provider = _implementation_budget_provider(
        monkeypatch,
        {"max_output_tokens": 16000},
    )

    assert provider._implementation_max_output_tokens() == 32000
    assert provider._implementation_retry_max_output_tokens() == 64000


def test_question_details_keep_exactly_one_recommendation() -> None:
    from ai_factory.openai_provider import normalize_question_details

    details = normalize_question_details(
        [
            {
                "question": "Qui peut réserver ?",
                "why": "Comptes ou pas.",
                "options": [
                    {"label": "Sans compte", "detail": "Simple.", "recommended": True},
                    {"label": "Avec compte", "detail": "Historique.", "recommended": True},
                ],
            },
            {
                "question": "Notification ?",
                "options": [
                    {"label": "E-mail", "detail": "Gratuit."},
                    {"label": "", "detail": "dropped"},
                ],
            },
            {"question": "   ", "options": []},
            "not a dict",
        ]
    )

    assert [d["question"] for d in details] == [
        "Qui peut réserver ?",
        "Notification ?",
    ]
    assert [o["recommended"] for o in details[0]["options"]] == [True, False]
    assert details[1]["options"] == [
        {"label": "E-mail", "detail": "Gratuit.", "recommended": True},
    ]
    assert details[1]["why"] == ""
    assert details[0]["needs_owner_text"] is False


def test_parse_result_merges_detailed_questions_into_questions(monkeypatch) -> None:
    import json

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider(model="test-model")

    result = provider._parse_result(
        json.dumps(
            {
                "status": "NEEDS_INPUT",
                "summary": "Questions.",
                "artifacts": [],
                "artifact_requests": [],
                "implementation_requests": [],
                "questions": [],
                "question_details": [
                    {
                        "question": "Quelle technique ?",
                        "why": "Langage et outils.",
                        "options": [
                            {"label": "Laisse le moteur choisir", "detail": "Recommandé.", "recommended": True},
                            {"label": "Je choisis", "detail": "Next.js…", "recommended": False},
                        ],
                    }
                ],
                "blockers": [],
                "handoff": None,
                "metadata": {"technology_proposal": None},
            }
        )
    )

    assert result.questions == ["Quelle technique ?"]
    assert result.question_details[0]["options"][0]["recommended"] is True


def test_question_details_keep_the_owner_text_flag() -> None:
    from ai_factory.openai_provider import normalize_question_details

    details = normalize_question_details(
        [
            {
                "question": "Quels sont tes horaires ?",
                "why": "Pour proposer les créneaux.",
                "needs_owner_text": True,
                "options": [
                    {"label": "Valeurs d'exemple", "detail": "Mar-Sam 9h-18h, modifiable.", "recommended": True},
                ],
            }
        ]
    )

    assert details[0]["needs_owner_text"] is True


def test_agent_prompt_forbids_options_that_only_promise_information(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider(model="test-model")
    captured = {}

    def fake_execute(prompt):
        captured["prompt"] = prompt
        raise RuntimeError("stop")

    provider._execute = fake_execute

    try:
        provider.run(
            {
                "agent_name": "product",
                "contract": "c",
                "project": {},
                "state": {},
            }
        )
    except RuntimeError:
        pass

    assert "only promises information later" in captured["prompt"]
    assert "needs_owner_text=true" in captured["prompt"]
    assert "Never block a first version on business data" in captured["prompt"]


def test_owner_summary_keeps_sentences_within_limits() -> None:
    from ai_factory.openai_provider import normalize_owner_summary

    summary = normalize_owner_summary(
        {
            "will_do": [f"Point {index}" for index in range(10)] + ["  "],
            "wont_do": [],
            "assumptions": ["Prix d'exemple : coupe 35 €", 3],
        }
    )

    assert len(summary["will_do"]) == 6
    assert "wont_do" not in summary
    assert summary["assumptions"] == ["Prix d'exemple : coupe 35 €"]
    assert normalize_owner_summary("nope") == {}


def _retry_provider(monkeypatch, outcomes):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "ai_factory.openai_provider.RateLimitError",
        _FakeRateLimitError,
    )
    provider = OpenAIProvider(model="test-model")
    waits = []
    provider._sleep = waits.append
    calls = {"count": 0}

    def create(**kwargs):
        outcome = outcomes[calls["count"]]
        calls["count"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider.client = type("C", (), {})()
    provider.client.responses = type("R", (), {"create": staticmethod(create)})()
    return provider, waits, calls


class _FakeRateLimitError(Exception):
    def __init__(self, code=None, retry_after=None):
        super().__init__("rate limited")
        self.code = code
        self.status_code = 429
        headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
        self.response = type("Resp", (), {"headers": headers})()


def _rate_limit_error(code=None, retry_after=None):
    return _FakeRateLimitError(code=code, retry_after=retry_after)


def test_rate_limit_is_retried_after_waiting(monkeypatch) -> None:
    ok = object()
    provider, waits, calls = _retry_provider(
        monkeypatch,
        [_rate_limit_error(), _rate_limit_error(retry_after=7), ok],
    )

    assert provider._create_response({"model": "m", "input": "x"}) is ok
    assert calls["count"] == 3
    assert waits == [20.0, 7.0]


def test_rate_limit_still_fails_after_the_last_retry(monkeypatch) -> None:
    from ai_factory.provider_errors import ProviderExecutionError

    provider, waits, calls = _retry_provider(
        monkeypatch,
        [_rate_limit_error() for _ in range(4)],
    )

    with pytest.raises(ProviderExecutionError, match="RATE_LIMITED"):
        provider._create_response({"model": "m", "input": "x"})

    assert calls["count"] == 4
    assert waits == [20.0, 40.0, 60.0]


def test_insufficient_quota_is_not_retried(monkeypatch) -> None:
    from ai_factory.provider_errors import ProviderExecutionError

    provider, waits, calls = _retry_provider(
        monkeypatch,
        [_rate_limit_error(code="insufficient_quota")],
    )

    with pytest.raises(ProviderExecutionError, match="insufficient quota"):
        provider._create_response({"model": "m", "input": "x"})

    assert calls["count"] == 1
    assert waits == []
