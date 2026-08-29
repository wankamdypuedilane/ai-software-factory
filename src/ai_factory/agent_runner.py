from pathlib import Path

from ai_factory.context_builder import build_agent_context
from ai_factory.providers import ModelProvider


def run_agent(
    project_root: Path,
    agent_name: str,
    provider: ModelProvider,
) -> str:
    """Build an agent context and execute it through a model provider."""

    context = build_agent_context(
        project_root=project_root,
        agent_name=agent_name,
    )

    return provider.run(context)
