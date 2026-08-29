import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

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

        env_path = (
            Path(__file__).resolve().parents[2]
            / ".env"
        )

        load_dotenv(
            dotenv_path=env_path,
            override=False,
        )

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required."
            )

        self.api_key = api_key
        self.client = OpenAI(
            api_key=self.api_key,
        )

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

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }

        max_output_tokens = self.settings.get(
            "max_output_tokens",
        )

        if max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = max_output_tokens

        response = self.client.responses.create(
            **request_kwargs,
        )

        return response.output_text
