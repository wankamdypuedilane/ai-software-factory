from typing import Any

from ai_factory.providers import (
    MockProvider,
    ModelProvider,
)


def create_provider(
    config: dict[str, Any],
) -> ModelProvider:
    """Create the configured AI model provider."""

    ai_config = config.get("ai")

    if not isinstance(ai_config, dict):
        raise ValueError(
            "Project configuration does not contain a valid ai section."
        )

    provider_name = ai_config.get("provider")

    if provider_name == "mock":
        return MockProvider()

    raise ValueError(
        f"Unsupported AI provider: {provider_name}"
    )
