from pathlib import Path
from typing import Any

from ai_factory.agent_runner import run_agent
from ai_factory.providers import MockProvider, ModelProvider
from ai_factory.state import save_state


class FakeProvider(ModelProvider):
    def __init__(self) -> None:
        self.received_context: dict[str, Any] | None = None

    def run(
        self,
        context: dict[str, Any],
    ) -> str:
        self.received_context = context
        return "fake-agent-output"


def test_run_agent_builds_context_and_calls_provider(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "architect": [],
                }
            },
        },
    )

    provider = FakeProvider()

    result = run_agent(
        project_root=tmp_path,
        agent_name="architect",
        provider=provider,
    )

    assert result == "fake-agent-output"

    assert provider.received_context is not None
    assert provider.received_context["agent_name"] == "architect"
    assert (
        provider.received_context["project"]["project"]["name"]
        == "Test Project"
    )
    assert (
        provider.received_context["state"]["agents"]["architect"]["status"]
        == "READY"
    )
    assert isinstance(
        provider.received_context["contract"],
        str,
    )


def test_mock_provider_returns_deterministic_output() -> None:
    provider = MockProvider()

    result = provider.run(
        {
            "agent_name": "architect",
        }
    )

    assert result.status == "COMPLETED"
    assert (
        result.summary
        == "Mock execution completed for agent: architect"
    )
    assert result.artifacts == []
    assert result.questions == []
    assert result.blockers == []
    assert result.handoff is None
