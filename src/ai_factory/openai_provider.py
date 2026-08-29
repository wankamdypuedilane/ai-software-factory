import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from ai_factory.agent_result import (
    AgentArtifact,
    AgentResult,
)
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
    ) -> AgentResult:
        """Execute an agent through OpenAI and return a structured result."""

        prompt = build_agent_prompt(context)

        structured_prompt = (
            prompt
            + "\n\n"
            + "## Required Output Format\n"
            + "Return ONLY valid JSON with this exact structure:\n"
            + "{\n"
            + '  "status": "COMPLETED | NEEDS_INPUT | BLOCKED | REVIEW_REQUIRED",\n'
            + '  "summary": "short summary",\n'
            + '  "artifacts": [\n'
            + "    {\n"
            + '      "path": "relative/project/path",\n'
            + '      "content": "artifact content"\n'
            + "    }\n"
            + "  ],\n"
            + '  "questions": [],\n'
            + '  "blockers": [],\n'
            + '  "handoff": null,\n'
            + '  "metadata": {}\n'
            + "}\n"
            + "Do not wrap the JSON in Markdown code fences."
        )

        raw_output = self._execute(
            structured_prompt,
        )

        return self._parse_result(
            raw_output,
        )

    def _parse_result(
        self,
        raw_output: str,
    ) -> AgentResult:
        """Parse a model response into an AgentResult."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned an invalid structured agent result."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "OpenAI agent result must be a JSON object."
            )

        artifacts_data = data.get(
            "artifacts",
            [],
        )

        if not isinstance(artifacts_data, list):
            raise ValueError(
                "Agent result artifacts must be a list."
            )

        artifacts = []

        for artifact_data in artifacts_data:
            if not isinstance(artifact_data, dict):
                raise ValueError(
                    "Invalid agent artifact."
                )

            path = artifact_data.get("path")
            content = artifact_data.get("content")

            if not isinstance(path, str) or not path.strip():
                raise ValueError(
                    "Agent artifact path is required."
                )

            if not isinstance(content, str):
                raise ValueError(
                    "Agent artifact content must be text."
                )

            artifacts.append(
                AgentArtifact(
                    path=path,
                    content=content,
                )
            )

        status = data.get("status")
        summary = data.get("summary")

        if not isinstance(status, str) or not status.strip():
            raise ValueError(
                "Agent result status is required."
            )

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "Agent result summary is required."
            )

        return AgentResult(
            status=status,
            summary=summary,
            artifacts=artifacts,
            questions=data.get("questions", []),
            blockers=data.get("blockers", []),
            handoff=data.get("handoff"),
            metadata=data.get("metadata", {}),
        )

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
