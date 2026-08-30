import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import (
    OpenAI,
    RateLimitError,
)

from ai_factory.agent_result import (
    AgentArtifact,
    AgentArtifactRequest,
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.prompt_builder import build_agent_prompt
from ai_factory.providers import ModelProvider


def build_implementation_result_schema() -> dict:
    """Build the strict JSON schema for implementation results."""

    return {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
            },
            "summary": {
                "type": "string",
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                        },
                        "content": {
                            "type": "string",
                        },
                        "operation": {
                            "type": "string",
                            "enum": [
                                "write",
                            ],
                        },
                    },
                    "required": [
                        "path",
                        "content",
                        "operation",
                    ],
                    "additionalProperties": False,
                },
            },
            "tests": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "blockers": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": [
            "task_id",
            "summary",
            "files",
            "tests",
            "blockers",
        ],
        "additionalProperties": False,
    }


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

    def generate(
        self,
        prompt: str,
    ) -> str:
        """Generate raw text content for a single artifact."""

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }

        max_output_tokens = self.settings.get(
            "max_output_tokens",
        )

        if max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = max_output_tokens

        try:
            response = self.client.responses.create(
                **request_kwargs,
            )
        except RateLimitError as error:
            raise ValueError(
                "OpenAI rate limit exceeded. "
                "Retry later or use a model/provider with available capacity."
            ) from error

        if response.status == "incomplete":
            incomplete_details = getattr(
                response,
                "incomplete_details",
                None,
            )

            raise ValueError(
                "OpenAI artifact response was incomplete. "
                f"Details: {incomplete_details}"
            )

        if not response.output_text:
            raise ValueError(
                "OpenAI returned no artifact content."
            )

        return response.output_text.strip()

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        """Execute one focused implementation task."""

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "implementation_result",
                    "strict": True,
                    "schema": build_implementation_result_schema(),
                }
            },
        }

        max_output_tokens = self.settings.get(
            "max_output_tokens"
        )

        if max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = max_output_tokens

        try:
            response = self.client.responses.create(
                **request_kwargs,
            )
        except RateLimitError as error:
            raise ValueError(
                "OpenAI rate limit exceeded. "
                "Retry later or use a model/provider with available capacity."
            ) from error

        if response.status == "incomplete":
            incomplete_details = getattr(
                response,
                "incomplete_details",
                None,
            )

            raise ValueError(
                "OpenAI implementation response was incomplete. "
                f"Details: {incomplete_details}"
            )

        if not response.output_text:
            raise ValueError(
                "OpenAI returned no implementation content."
            )

        return self._parse_implementation_result(
            response.output_text,
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
            + '  "artifacts": [],\n'
            + '  "artifact_requests": [\n'
            + "    {\n"
            + '      "path": "relative/project/path",\n'
            + '      "purpose": "what this artifact must document or produce"\n'
            + "    }\n"
            + "  ],\n"
            + '  "questions": [],\n'
            + '  "blockers": [],\n'
            + '  "handoff": null,\n'
            + '  "metadata": {}\n'
            + "}\n\n"
            + "Artifact policy:\n"
            + "- Keep artifacts empty unless the artifact content is very small.\n"
            + "- Do NOT generate large document contents inside this response.\n"
            + "- Use artifact_requests to declare documents or files that should "
            + "be generated separately by the Factory.\n"
            + "- Each artifact request must include a project-relative path and "
            + "a concise purpose.\n"
            + "- Keep the overall response concise.\n"
            + "Do not wrap the JSON in Markdown code fences."
        )

        if context.get("agent_name") == "architect":
            structured_prompt += (
                "\n\n"
                "## Architect Technology Proposal Requirement\n"
                "Because this project may require a Technology Gate, "
                "include a technology proposal in metadata using this structure:\n"
                "{\n"
                '  "technology_proposal": {\n'
                '    "components": {\n'
                '      "component_name": {\n'
                '        "technology": "selected technology",\n'
                '        "rationale": "concise justification"\n'
                "      }\n"
                "    }\n"
                "  }\n"
                "}\n"
                "Include only components that are relevant to the project. "
                "Base every recommendation on the supplied requirements, "
                "constraints, UX/UI artifacts, and architecture context."
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

        artifact_requests_data = data.get(
            "artifact_requests",
            [],
        )

        if not isinstance(artifact_requests_data, list):
            raise ValueError(
                "Agent result artifact requests must be a list."
            )

        artifact_requests = []

        for request_data in artifact_requests_data:
            if not isinstance(request_data, dict):
                raise ValueError(
                    "Invalid agent artifact request."
                )

            path = request_data.get("path")
            purpose = request_data.get("purpose")

            if not isinstance(path, str) or not path.strip():
                raise ValueError(
                    "Agent artifact request path is required."
                )

            if not isinstance(purpose, str) or not purpose.strip():
                raise ValueError(
                    "Agent artifact request purpose is required."
                )

            artifact_requests.append(
                AgentArtifactRequest(
                    path=path,
                    purpose=purpose,
                )
            )

        implementation_requests_data = data.get(
            "implementation_requests",
            [],
        )

        if not isinstance(implementation_requests_data, list):
            raise ValueError(
                "Agent result implementation requests must be a list."
            )

        implementation_requests = []

        for request_data in implementation_requests_data:
            if not isinstance(request_data, dict):
                raise ValueError(
                    "Invalid agent implementation request."
                )

            request_id = request_data.get("id")
            title = request_data.get("title")
            purpose = request_data.get("purpose")

            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError(
                    "Implementation request id is required."
                )

            if not isinstance(title, str) or not title.strip():
                raise ValueError(
                    "Implementation request title is required."
                )

            if not isinstance(purpose, str) or not purpose.strip():
                raise ValueError(
                    "Implementation request purpose is required."
                )

            implementation_requests.append(
                AgentImplementationRequest(
                    id=request_id,
                    title=title,
                    purpose=purpose,
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
            artifact_requests=artifact_requests,
            implementation_requests=implementation_requests,
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

        request_kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": "agent_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": [
                                "COMPLETED",
                                "NEEDS_INPUT",
                                "BLOCKED",
                                "REVIEW_REQUIRED",
                            ],
                        },
                        "summary": {
                            "type": "string",
                        },
                        "artifacts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                    },
                                    "content": {
                                        "type": "string",
                                    },
                                },
                                "required": [
                                    "path",
                                    "content",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "artifact_requests": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                    },
                                    "purpose": {
                                        "type": "string",
                                    },
                                },
                                "required": [
                                    "path",
                                    "purpose",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "implementation_requests": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {
                                        "type": "string",
                                    },
                                    "title": {
                                        "type": "string",
                                    },
                                    "purpose": {
                                        "type": "string",
                                    },
                                },
                                "required": [
                                    "id",
                                    "title",
                                    "purpose",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                        },
                        "blockers": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                        },
                        "handoff": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "technology_proposal": {
                                    "type": "object",
                                    "properties": {
                                        "components": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {
                                                        "type": "string",
                                                    },
                                                    "technology": {
                                                        "type": "string",
                                                    },
                                                    "rationale": {
                                                        "type": "string",
                                                    },
                                                },
                                                "required": [
                                                    "name",
                                                    "technology",
                                                    "rationale",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                    },
                                    "required": [
                                        "components",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                            "required": [
                                "technology_proposal",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "required": [
                        "status",
                        "summary",
                        "artifacts",
                        "artifact_requests",
                        "implementation_requests",
                        "questions",
                        "blockers",
                        "handoff",
                        "metadata",
                    ],
                    "additionalProperties": False,
                },
            }
        }

        max_output_tokens = self.settings.get(
            "max_output_tokens",
        )

        if max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = max_output_tokens

        try:
            response = self.client.responses.create(
                **request_kwargs,
            )
        except RateLimitError as error:
            raise ValueError(
                "OpenAI rate limit exceeded. "
                "Retry later or use a model/provider with available capacity."
            ) from error

        if response.status == "incomplete":
            incomplete_details = getattr(
                response,
                "incomplete_details",
                None,
            )

            raise ValueError(
                "OpenAI response was incomplete. "
                f"Details: {incomplete_details}"
            )

        if not response.output_text:
            raise ValueError(
                "OpenAI returned no text output."
            )

        return response.output_text

    def _parse_implementation_result(
        self,
        raw_output: str,
    ) -> ImplementationResult:
        """Parse a structured implementation result."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned invalid implementation JSON."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "Implementation result must be an object."
            )

        task_id = data.get("task_id")
        summary = data.get("summary")
        files_data = data.get("files", [])
        tests = data.get("tests", [])
        blockers = data.get("blockers", [])

        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(
                "Implementation result task_id is required."
            )

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "Implementation result summary is required."
            )

        if not isinstance(files_data, list):
            raise ValueError(
                "Implementation result files must be a list."
            )

        if not isinstance(tests, list) or not all(
            isinstance(test, str)
            for test in tests
        ):
            raise ValueError(
                "Implementation result tests must be a list of strings."
            )

        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str)
            for blocker in blockers
        ):
            raise ValueError(
                "Implementation result blockers must be a list of strings."
            )

        files: list[ImplementationFileChange] = []

        for file_data in files_data:
            if not isinstance(file_data, dict):
                raise ValueError(
                    "Invalid implementation file change."
                )

            path = file_data.get("path")
            content = file_data.get("content")
            operation = file_data.get("operation")

            if not isinstance(path, str) or not path.strip():
                raise ValueError(
                    "Implementation file path is required."
                )

            if not isinstance(content, str):
                raise ValueError(
                    "Implementation file content must be a string."
                )

            if operation != "write":
                raise ValueError(
                    f"Unsupported implementation operation: {operation}"
                )

            files.append(
                ImplementationFileChange(
                    path=path,
                    content=content,
                    operation=operation,
                )
            )

        return ImplementationResult(
            task_id=task_id,
            summary=summary,
            files=files,
            tests=tests,
            blockers=blockers,
        )
