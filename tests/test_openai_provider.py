import pytest

from ai_factory.openai_provider import (
    OpenAIProvider,
    build_devops_result_schema,
    build_implementation_result_schema,
    build_qa_result_schema,
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
                "purpose": "Implement authentication with automated tests."
            },
            {
                "id": "US-002",
                "title": "Ride request workflow",
                "purpose": "Implement ride creation and status handling."
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
        "tests",
        "blockers",
    }

    properties = schema["properties"]

    assert "task_id" in properties
    assert "summary" in properties
    assert "files" in properties
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
    assert captured["max_output_tokens"] == 2500

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
