from typing import Any

from ai_factory.openai_provider import OpenAIProvider
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

    if provider_name == "openai":
        model = ai_config.get("model")
        settings = ai_config.get("settings", {})

        return OpenAIProvider(
            model=model,
            settings=settings,
        )

    raise ValueError(
        f"Unsupported AI provider: {provider_name}"
    )
