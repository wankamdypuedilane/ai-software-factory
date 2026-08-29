import os
from typing import Any

from ai_factory.prompt_builder import build_agent_prompt
from ai_factory.providers import ModelProvider


class OpenAIProvider(ModelProvider):
    """OpenAI-backed model provider."""

    def __init__(
        self,
        model: str,
        settings: dict[str, Any] | None = None,
    ) -> None:
        if not model:
            raise ValueError(
                "OpenAI model must be configured."
            )

        self.model = model
        self.settings = settings or {}

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required."
            )

        self.api_key = api_key

    def run(
        self,
        context: dict[str, Any],
    ) -> str:
        """Execute an agent through OpenAI."""

        prompt = build_agent_prompt(context)

        return self._execute(prompt)

    def _execute(
        self,
        prompt: str,
    ) -> str:
        """Send a prepared prompt to OpenAI."""

        raise NotImplementedError(
            "OpenAI API execution is not implemented yet."
        )
