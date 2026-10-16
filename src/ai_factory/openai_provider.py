import functools
import json
import time
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from ai_factory.blocker_contract import (
    BLOCKER_KIND_VALUES,
    BLOCKER_SCOPE_VALUES,
    coerce_blockers,
    normalize_blockers,
    validate_declared_blockers,
)
from ai_factory.agent_result import (
    AgentArtifact,
    AgentArtifactRequest,
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.implementation_contract import (
    SCOPE_VALUES,
    TASK_KIND_VALUES,
    clamp_verification_policy,
    coerce_scope,
    coerce_task_kind,
    coerce_verification_policy,
    validate_declared_contracts,
)
from ai_factory.devops_result import (
    DevOpsChange,
    DevOpsResult,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.qa_result import (
    QADefect,
    QAResult,
)
from ai_factory.sre_result import (
    SREFinding,
    SREResult,
)
from ai_factory.security_result import (
    SecurityFinding,
    SecurityResult,
)
from ai_factory.prompt_builder import build_agent_prompt
from ai_factory.providers import DevelopmentModelProvider
from ai_factory.resources import get_source_checkout_dir
from ai_factory.provider_errors import (
    ProviderErrorKind,
    ProviderExecutionError,
    ProviderResultError,
    kind_for_status_code,
)


def parses_provider_result(stage: str):
    """Attribute every parsing refusal of `stage` to the provider result.

    A response that does not satisfy the structural contract is a provider
    result failure, not an operator mistake and not a Factory crash. Naming
    it keeps the CLI able to report it as such, and keeps the failure
    recoverable: parsing happens before anything is applied.
    """

    def decorator(function):
        @functools.wraps(function)
        def wrapper(self, raw_output):
            try:
                return function(self, raw_output)
            except (ProviderResultError, ProviderExecutionError):
                raise
            except ValueError as error:
                raise ProviderResultError(
                    stage=stage,
                    message=str(error),
                ) from error

        return wrapper

    return decorator


QUOTA_CODES = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active"}
QUOTA_MESSAGES = ("exceeded your current quota", "check your plan and billing", "billing details")


def _is_insufficient_quota(error: Exception) -> bool:
    """Whether a provider error means the account has no credit left.

    A real run with a negative balance surfaced as RATE_LIMITED: the
    code field alone is not reliable, so the type and the message are
    checked too.
    """

    for field in ("code", "type"):
        value = getattr(error, field, None)

        if isinstance(value, str) and value in QUOTA_CODES:
            return True

    body = getattr(error, "body", None)

    if isinstance(body, dict):
        nested = body.get("error") if isinstance(body.get("error"), dict) else body

        for field in ("code", "type"):
            if nested.get(field) in QUOTA_CODES:
                return True

    message = str(getattr(error, "message", "") or error).lower()

    return any(marker in message for marker in QUOTA_MESSAGES)


def classify_openai_error(
    error: Exception,
) -> ProviderExecutionError:
    """Classify a provider transport failure by type and status code."""

    # An exhausted balance is reported as a 429 too, but waiting never
    # fixes it. The error code is a structured field of the response body.
    if _is_insufficient_quota(error):
        return ProviderExecutionError(
            kind=ProviderErrorKind.PERMANENT_REQUEST,
            message=(
                "OpenAI reports insufficient quota: the account has no "
                "credit left. Add credit in the OpenAI billing settings."
            ),
            status_code=getattr(error, "status_code", 429),
        )

    if isinstance(error, RateLimitError):
        return ProviderExecutionError(
            kind=ProviderErrorKind.RATE_LIMITED,
            message=(
                "OpenAI rate limit exceeded. "
                "Retry later or use a model/provider with "
                "available capacity."
            ),
            status_code=getattr(error, "status_code", 429),
        )

    if isinstance(
        error,
        (
            APITimeoutError,
            APIConnectionError,
        ),
    ):
        return ProviderExecutionError(
            kind=ProviderErrorKind.NETWORK,
            message=f"OpenAI request did not complete: {error}",
        )

    if isinstance(error, APIStatusError):
        status_code = getattr(
            error,
            "status_code",
            None,
        )

        return ProviderExecutionError(
            kind=kind_for_status_code(status_code),
            message=f"OpenAI rejected the request: {error}",
            status_code=status_code,
        )

    return ProviderExecutionError(
        kind=ProviderErrorKind.UNKNOWN,
        message=f"OpenAI call failed: {error}",
    )


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
            "setup_commands": {
                "type": "array",
                "items": {
                    "type": "string",
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
            "setup_commands",
            "tests",
            "blockers",
        ],
        "additionalProperties": False,
    }


def build_qa_result_schema() -> dict:
    """Build the strict JSON schema for QA results."""

    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
            },
            "passed": {
                "type": "boolean",
            },
            "defects": {
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
                        "severity": {
                            "type": "string",
                            "enum": [
                                "Critical",
                                "High",
                                "Medium",
                                "Low",
                            ],
                        },
                        "related_story": {
                            "type": "string",
                        },
                        "expected": {
                            "type": "string",
                        },
                        "actual": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "id",
                        "title",
                        "severity",
                        "related_story",
                        "expected",
                        "actual",
                    ],
                    "additionalProperties": False,
                },
            },
            "test_commands": {
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
            "summary",
            "passed",
            "defects",
            "test_commands",
            "blockers",
        ],
        "additionalProperties": False,
    }


def build_security_result_schema() -> dict:
    """Build the strict JSON schema for security results."""

    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
            },
            "passed": {
                "type": "boolean",
            },
            "findings": {
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
                        "severity": {
                            "type": "string",
                            "enum": [
                                "Critical",
                                "High",
                                "Medium",
                                "Low",
                                "Informational",
                            ],
                        },
                        "affected_component": {
                            "type": "string",
                        },
                        "description": {
                            "type": "string",
                        },
                        "impact": {
                            "type": "string",
                        },
                        "evidence": {
                            "type": "string",
                        },
                        "recommended_remediation": {
                            "type": "string",
                        },
                        "priority": {
                            "type": "string",
                        },
                        "status": {
                            "type": "string",
                        },
                    },
                    "required": [
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
                    ],
                    "additionalProperties": False,
                },
            },
            "test_commands": {
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
            "summary",
            "passed",
            "findings",
            "test_commands",
            "blockers",
        ],
        "additionalProperties": False,
    }


def build_devops_result_schema() -> dict:
    """Build the strict JSON schema for DevOps results."""

    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
            },
            "passed": {
                "type": "boolean",
            },
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                        },
                        "description": {
                            "type": "string",
                        },
                        "category": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "path",
                        "description",
                        "category",
                    ],
                    "additionalProperties": False,
                },
            },
            "test_commands": {
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
            "deployment_ready": {
                "type": "boolean",
            },
            "rollback_strategy": {
                "type": "string",
            },
        },
        "required": [
            "summary",
            "passed",
            "changes",
            "test_commands",
            "blockers",
            "deployment_ready",
            "rollback_strategy",
        ],
        "additionalProperties": False,
    }


def build_sre_result_schema() -> dict:
    """Build the strict JSON schema for SRE results."""

    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
            },
            "passed": {
                "type": "boolean",
            },
            "findings": {
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
                        "severity": {
                            "type": "string",
                            "enum": [
                                "Critical",
                                "High",
                                "Medium",
                                "Low",
                                "Informational",
                            ],
                        },
                        "category": {
                            "type": "string",
                        },
                        "description": {
                            "type": "string",
                        },
                        "recommendation": {
                            "type": "string",
                        },
                        "status": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "id",
                        "title",
                        "severity",
                        "category",
                        "description",
                        "recommendation",
                        "status",
                    ],
                    "additionalProperties": False,
                },
            },
            "test_commands": {
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
            "observability_ready": {
                "type": "boolean",
            },
            "incident_readiness": {
                "type": "boolean",
            },
        },
        "required": [
            "summary",
            "passed",
            "findings",
            "test_commands",
            "blockers",
            "observability_ready",
            "incident_readiness",
        ],
        "additionalProperties": False,
    }


def build_agent_result_schema() -> dict:
    """Build the strict JSON schema for agent results."""

    return {
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
                        "kind": {
                            "type": [
                                "string",
                                "null",
                            ],
                            "enum": [
                                *TASK_KIND_VALUES,
                                None,
                            ],
                        },
                        "scope": {
                            "type": [
                                "string",
                                "null",
                            ],
                            "enum": [
                                *SCOPE_VALUES,
                                None,
                            ],
                        },
                        "verification": {
                            "type": [
                                "object",
                                "null",
                            ],
                            "properties": {
                                "allow_full_suite": {
                                    "type": "boolean",
                                },
                                "baseline_required": {
                                    "type": "boolean",
                                },
                            },
                            "required": [
                                "allow_full_suite",
                                "baseline_required",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "required": [
                        "id",
                        "title",
                        "purpose",
                        "kind",
                        "scope",
                        "verification",
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
            "question_details": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                        },
                        "why": {
                            "type": "string",
                        },
                        "needs_owner_text": {
                            "type": "boolean",
                        },
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                    },
                                    "detail": {
                                        "type": "string",
                                    },
                                    "recommended": {
                                        "type": "boolean",
                                    },
                                },
                                "required": [
                                    "label",
                                    "detail",
                                    "recommended",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "question",
                        "why",
                        "needs_owner_text",
                        "options",
                    ],
                    "additionalProperties": False,
                },
            },
            "owner_summary": {
                "type": "object",
                "properties": {
                    "will_do": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "wont_do": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "assumptions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "will_do",
                    "wont_do",
                    "assumptions",
                ],
                "additionalProperties": False,
            },
            "blockers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                        },
                        "kind": {
                            "type": "string",
                            "enum": list(
                                BLOCKER_KIND_VALUES
                            ),
                        },
                        "scope": {
                            "type": "string",
                            "enum": list(
                                BLOCKER_SCOPE_VALUES
                            ),
                        },
                        "fixable_by_agent": {
                            "type": "boolean",
                        },
                        "requires_human_input": {
                            "type": "boolean",
                        },
                        "blocking": {
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "message",
                        "kind",
                        "scope",
                        "fixable_by_agent",
                        "requires_human_input",
                        "blocking",
                    ],
                    "additionalProperties": False,
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
                        "type": [
                            "object",
                            "null",
                        ],
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
            "question_details",
            "owner_summary",
            "blockers",
            "handoff",
            "metadata",
        ],
        "additionalProperties": False,
    }


# Floor for an implementation unit's output budget when only the shared
# budget is configured. Raised from a real run where 16000 tokens truncated a
# single command-line module.
DEFAULT_IMPLEMENTATION_MAX_OUTPUT_TOKENS = 32000


OWNER_SUMMARY_LIMITS = {
    "will_do": 6,
    "wont_do": 4,
    "assumptions": 5,
}


def normalize_owner_summary(
    raw: Any,
) -> dict[str, list[str]]:
    """Keep the owner summary's non-empty sentences, within its limits."""

    if not isinstance(raw, dict):
        return {}

    summary: dict[str, list[str]] = {}

    for key, limit in OWNER_SUMMARY_LIMITS.items():
        values = raw.get(key)

        if not isinstance(values, list):
            continue

        cleaned = [
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ][:limit]

        if cleaned:
            summary[key] = cleaned

    return summary


def normalize_question_details(
    raw: Any,
) -> list[dict[str, Any]]:
    """Keep well-formed question details, with exactly one recommendation.

    Malformed entries are dropped rather than failing the whole result: the
    plain question list still carries every question.
    """

    if not isinstance(raw, list):
        return []

    details: list[dict[str, Any]] = []

    for entry in raw:
        if not isinstance(entry, dict):
            continue

        question = entry.get("question")

        if not isinstance(question, str) or not question.strip():
            continue

        options = []

        for option in entry.get("options", []) or []:
            if not isinstance(option, dict):
                continue

            label = option.get("label")

            if not isinstance(label, str) or not label.strip():
                continue

            options.append(
                {
                    "label": label.strip(),
                    "detail": str(option.get("detail") or "").strip(),
                    "recommended": option.get("recommended") is True,
                }
            )

        recommended = [
            index
            for index, option in enumerate(options)
            if option["recommended"]
        ]

        # Exactly one recommendation: the first one claimed, else the first
        # option, so an interface always has a default to preselect.
        if options:
            keep = recommended[0] if recommended else 0

            for index, option in enumerate(options):
                option["recommended"] = index == keep

        details.append(
            {
                "question": question.strip(),
                "why": str(entry.get("why") or "").strip(),
                "needs_owner_text": entry.get("needs_owner_text") is True,
                "options": options,
            }
        )

    return details


# Waits before each retry of a transient provider failure. Per-minute rate
# limits need tens of seconds, not the SDK's sub-second backoff.
DEFAULT_RETRY_DELAYS_SECONDS = (20.0, 40.0, 60.0)
MAX_RETRY_AFTER_SECONDS = 120.0


def _retry_after_seconds(error: Exception) -> float | None:
    """Return the provider's Retry-After hint, when it sent one."""

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)

    if headers is None:
        return None

    try:
        value = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None

    if value < 0:
        return None

    return min(value, MAX_RETRY_AFTER_SECONDS)


class OpenAIProvider(DevelopmentModelProvider):
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

        # Project-local .env first, then the Factory checkout's .env.
        for env_path in (
            Path.cwd() / ".env",
            get_source_checkout_dir() / ".env",
        ):
            if env_path.is_file():
                load_dotenv(
                    dotenv_path=env_path,
                    override=False,
                )

        api_key_env = self.settings.get("api_key_env")

        if api_key_env is None:
            api_key_env = "OPENAI_API_KEY"

        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise ValueError(
                "ai.settings.api_key_env must be a non-empty "
                "environment variable name."
            )

        base_url = self.settings.get("base_url")

        if base_url is not None and (
            not isinstance(base_url, str) or not base_url.strip()
        ):
            raise ValueError(
                "ai.settings.base_url must be a non-empty URL."
            )

        api_key = os.getenv(api_key_env)

        if not api_key:
            raise ValueError(
                f"{api_key_env} environment variable is required."
            )

        self.api_key = api_key
        self.api_key_env = api_key_env
        self.base_url = base_url

        client_kwargs: dict[str, Any] = {
            "api_key": self.api_key,
        }

        # Left out when unset so the SDK keeps its own default endpoint,
        # including an OPENAI_BASE_URL from the environment.
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(
            **client_kwargs,
        )

    def generate(
        self,
        prompt: str,
    ) -> str:
        """Generate raw text content for a single artifact."""

        return self._request(
            prompt,
            label="artifact",
            max_output_tokens=self._max_output_tokens(
                "artifact_max_output_tokens"
            ),
        ).strip()

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        """Execute one focused implementation task."""

        raw_output = self._request(
            prompt,
            label="implementation",
            schema_name="implementation_result",
            schema=build_implementation_result_schema(),
            max_output_tokens=self._implementation_max_output_tokens(),
            retry_max_output_tokens=(
                self._implementation_retry_max_output_tokens()
            ),
        )

        return self._parse_implementation_result(
            raw_output,
        )

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        """Execute structured QA validation."""

        raw_output = self._request(
            prompt,
            label="QA",
            schema_name="qa_result",
            schema=build_qa_result_schema(),
            max_output_tokens=self._max_output_tokens(),
        )

        return self._parse_qa_result(
            raw_output,
        )

    def validate_security(
        self,
        prompt: str,
    ) -> SecurityResult:
        """Execute structured security validation."""

        raw_output = self._request(
            prompt,
            label="security",
            schema_name="security_result",
            schema=build_security_result_schema(),
            max_output_tokens=self._max_output_tokens(),
        )

        return self._parse_security_result(
            raw_output,
        )

    def validate_devops(
        self,
        prompt: str,
    ) -> DevOpsResult:
        """Execute structured DevOps validation."""

        raw_output = self._request(
            prompt,
            label="DevOps",
            schema_name="devops_result",
            schema=build_devops_result_schema(),
            max_output_tokens=self._max_output_tokens(),
        )

        return self._parse_devops_result(
            raw_output,
        )

    def validate_sre(
        self,
        prompt: str,
    ) -> SREResult:
        """Execute structured SRE validation."""

        raw_output = self._request(
            prompt,
            label="SRE",
            schema_name="sre_result",
            schema=build_sre_result_schema(),
            max_output_tokens=self._max_output_tokens(),
        )

        return self._parse_sre_result(
            raw_output,
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
            + '  "implementation_requests": [\n'
            + "    {\n"
            + '      "id": "implementation-task-id",\n'
            + '      "title": "short implementation task title",\n'
            + '      "purpose": "what should be implemented",\n'
            + '      "kind": "IMPLEMENTATION | TEST_IMPLEMENTATION '
            + '| VERIFICATION",\n'
            + '      "scope": "TASK | PROJECT",\n'
            + '      "verification": {\n'
            + '        "allow_full_suite": false,\n'
            + '        "baseline_required": true\n'
            + "      }\n"
            + "    }\n"
            + "  ],\n"
            + '  "questions": [],\n'
            + '  "question_details": [],\n'
            + '  "owner_summary": {"will_do": [], "wont_do": [], "assumptions": []},\n'
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
            + "Implementation task contract:\n"
            + "- kind: IMPLEMENTATION produces source, TEST_IMPLEMENTATION "
            + "produces automated tests, VERIFICATION validates work that "
            + "already exists.\n"
            + "- scope: TASK covers one unit, PROJECT covers the whole "
            + "project.\n"
            + "- verification.allow_full_suite: true only for a "
            + "VERIFICATION unit with PROJECT scope; every other unit must "
            + "declare false and validate itself with task-scoped "
            + "commands.\n"
            + "- verification.baseline_required: true for every unit that "
            + "changes the project, so an unrelated pre-existing failure "
            + "cannot be attributed to it.\n"
            + "- The Factory derives execution policy from these fields "
            + "only, never from the title or the purpose.\n"
            + "Owner summary (owner_summary):\n"
            + "- Written for a project owner who does not read code, in the "
            + "language of the human input, with no file names, code or "
            + "jargon.\n"
            + "- will_do: up to 6 short sentences on what your step decided, "
            + "built or verified, as it affects the product.\n"
            + "- wont_do: up to 4 things deliberately left out of this "
            + "version.\n"
            + "- assumptions: up to 5 things you decided on the owner's "
            + "behalf that they should check (example values, defaults).\n"
            + "Questions to the human:\n"
            + "- For every entry in questions, add one entry to "
            + "question_details with the same question text, a one-sentence "
            + "why in plain language, and 2 to 4 options.\n"
            + "- Each option has a short label, a one-sentence detail that "
            + "states its consequence (cost, effort, what the user gets), "
            + "and recommended=true on exactly one option: the safest "
            + "sensible default for someone who does not code.\n"
            + "- Write questions and options in the language of the human "
            + "input, without technical jargon unless the human uses it.\n"            + "- Every option must be a complete answer you can act on "
            + "immediately. Never offer an option that only promises "
            + "information later (such as 'I will provide the list' or "
            + "'decide later').\n"
            + "- When the answer is information only the owner has (a list "
            + "of services, prices, opening hours, names, texts), set "
            + "needs_owner_text=true and make the options concrete example "
            + "answers the owner can pick as they are.\n"
            + "- Never block a first version on business data: make the "
            + "recommended option 'use clearly marked example values that "
            + "the owner edits later' and state those example values in "
            + "its detail.\n"
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
                '    "components": [\n'
                "      {\n"
                '        "name": "component_name",\n'
                '        "technology": "selected technology",\n'
                '        "rationale": "concise justification"\n'
                "      }\n"
                "    ]\n"
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

    @parses_provider_result("agent_result")
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

            kind = coerce_task_kind(
                request_data.get("kind")
            )

            scope = coerce_scope(
                request_data.get("scope")
            )

            implementation_requests.append(
                AgentImplementationRequest(
                    id=request_id,
                    title=title,
                    purpose=purpose,
                    kind=kind,
                    scope=scope,
                    # Reduced to what the declared kind and scope permit
                    # before anything can read it as authority.
                    verification=clamp_verification_policy(
                        kind=kind,
                        scope=scope,
                        verification=coerce_verification_policy(
                            request_data.get("verification")
                        ),
                    ),
                )
            )

        validate_declared_contracts(
            implementation_requests
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

        declared_blockers = data.get("blockers", [])

        validate_declared_blockers(
            declared_blockers
        )

        blockers, harvested_questions = normalize_blockers(
            coerce_blockers(
                declared_blockers
            )
        )

        questions = list(
            data.get("questions", [])
        )

        # A blocker that only needs a human decision is surfaced through the
        # channel that can actually be answered.
        questions.extend(
            question
            for question in harvested_questions
            if question not in questions
        )

        question_details = normalize_question_details(
            data.get("question_details", []),
        )

        # Every detailed question is also a plain question, so callers that
        # only read `questions` (the CLI, the state) never miss one.
        questions.extend(
            detail["question"]
            for detail in question_details
            if detail["question"] not in questions
        )

        owner_summary = normalize_owner_summary(
            data.get("owner_summary"),
        )

        return AgentResult(
            status=status,
            summary=summary,
            owner_summary=owner_summary,
            artifacts=artifacts,
            artifact_requests=artifact_requests,
            implementation_requests=implementation_requests,
            questions=questions,
            question_details=question_details,
            blockers=blockers,
            handoff=data.get("handoff"),
            metadata=data.get("metadata", {}),
        )

    def _execute(
        self,
        prompt: str,
    ) -> str:
        """Send a prepared agent prompt to OpenAI."""

        return self._request(
            prompt,
            label=None,
            schema_name="agent_result",
            schema=build_agent_result_schema(),
            max_output_tokens=self._max_output_tokens(
                "agent_max_output_tokens"
            ),
        )

    def _max_output_tokens(
        self,
        specific_key: str | None = None,
    ) -> Any:
        """Resolve a stage-specific token budget, then the shared one."""

        if specific_key is None:
            return self.settings.get("max_output_tokens")

        return self.settings.get(
            specific_key,
            self.settings.get(
                "max_output_tokens",
            ),
        )

    def _implementation_max_output_tokens(self) -> Any:
        """Resolve the token budget of one implementation unit.

        A unit returns complete files inside a JSON document, which needs far
        more room than any other stage. A shared budget sized for summaries
        is therefore raised to a floor instead of truncating the code.
        """

        explicit = self.settings.get(
            "implementation_max_output_tokens"
        )

        if explicit is not None:
            return explicit

        shared = self.settings.get("max_output_tokens")

        if not isinstance(shared, int) or isinstance(shared, bool):
            return shared

        return max(
            shared,
            DEFAULT_IMPLEMENTATION_MAX_OUTPUT_TOKENS,
        )

    def _implementation_retry_max_output_tokens(self) -> Any:
        """Resolve the budget of the single retry of a truncated unit."""

        explicit = self.settings.get(
            "implementation_retry_max_output_tokens"
        )

        if explicit is not None:
            return explicit

        first = self._implementation_max_output_tokens()

        if not isinstance(first, int) or isinstance(first, bool):
            return None

        return first * 2

    def _request(
        self,
        prompt: str,
        *,
        label: str | None,
        schema_name: str | None = None,
        schema: dict | None = None,
        max_output_tokens: Any = None,
        retry_max_output_tokens: Any = None,
    ) -> str:
        """Call the Responses API and return its non-empty text output.

        Every OpenAI call goes through here: transport failures, rate limits
        included, are classified; an output truncated by its token budget is
        retried once when a different retry budget is configured; an
        incomplete or empty response is refused. `label` names the stage in
        error messages, and None stands for the agent call itself.
        """

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }

        if schema is not None:
            request_kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            }

        if max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = max_output_tokens

        response = self._create_response(request_kwargs)

        if (
            response.status == "incomplete"
            and retry_max_output_tokens is not None
            and retry_max_output_tokens != max_output_tokens
        ):
            incomplete_details = getattr(
                response,
                "incomplete_details",
                None,
            )

            reason = getattr(
                incomplete_details,
                "reason",
                incomplete_details,
            )

            if reason == "max_output_tokens":
                response = self._create_response(
                    {
                        **request_kwargs,
                        "max_output_tokens": retry_max_output_tokens,
                    }
                )

        if response.status == "incomplete":
            incomplete_details = getattr(
                response,
                "incomplete_details",
                None,
            )

            subject = (
                f"OpenAI {label} response"
                if label
                else "OpenAI response"
            )

            raise ValueError(
                f"{subject} was incomplete. "
                f"Details: {incomplete_details}. "
                "If the reason is max_output_tokens, raise "
                "ai.settings.max_output_tokens (or the stage-specific "
                "budget) in .factory/project.yaml and relaunch."
            )

        if not response.output_text:
            raise ValueError(
                f"OpenAI returned no {label} content."
                if label
                else "OpenAI returned no text output."
            )

        return response.output_text

    def _create_response(
        self,
        request_kwargs: dict[str, Any],
    ) -> Any:
        """Send one request, waiting and retrying on transient failures.

        Rate limits are per minute, so the SDK's own sub-second retries do
        not outlast them: a real run stopped on RATE_LIMITED in the middle
        of the Developer phase. Retryable failures (rate limit, server
        error, network) wait and try again a bounded number of times;
        everything else is raised at once.
        """

        delays = self._retry_delays()

        for attempt in range(len(delays) + 1):
            try:
                return self.client.responses.create(
                    **request_kwargs,
                )
            except Exception as error:
                classified = classify_openai_error(error)

                if not classified.retryable or attempt >= len(delays):
                    raise classified from error

                self._sleep(
                    _retry_after_seconds(error) or delays[attempt]
                )

        raise AssertionError("unreachable")

    def _retry_delays(self) -> list[float]:
        configured = self.settings.get("provider_retry_delays_seconds")

        if isinstance(configured, list) and all(
            isinstance(value, (int, float)) and value >= 0
            for value in configured
        ):
            return [float(value) for value in configured]

        return list(DEFAULT_RETRY_DELAYS_SECONDS)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    @parses_provider_result("implementation_result")
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
        setup_commands = data.get(
            "setup_commands",
            [],
        )
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

        if not isinstance(setup_commands, list) or not all(
            isinstance(command, str)
            for command in setup_commands
        ):
            raise ValueError(
                "Implementation result setup_commands must be a list of strings."
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
            setup_commands=setup_commands,
            tests=tests,
            blockers=blockers,
        )

    @parses_provider_result("qa_result")
    def _parse_qa_result(
        self,
        raw_output: str,
    ) -> QAResult:
        """Parse a structured QA result."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned invalid QA JSON."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "QA result must be an object."
            )

        summary = data.get("summary")
        passed = data.get("passed")
        defects_data = data.get("defects", [])
        test_commands = data.get(
            "test_commands",
            [],
        )
        blockers = data.get("blockers", [])

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "QA result summary is required."
            )

        if not isinstance(passed, bool):
            raise ValueError(
                "QA result passed must be a boolean."
            )

        if not isinstance(defects_data, list):
            raise ValueError(
                "QA result defects must be a list."
            )

        if not isinstance(test_commands, list) or not all(
            isinstance(command, str)
            for command in test_commands
        ):
            raise ValueError(
                "QA result test_commands must be a list of strings."
            )

        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str)
            for blocker in blockers
        ):
            raise ValueError(
                "QA result blockers must be a list of strings."
            )

        defects: list[QADefect] = []

        valid_severities = {
            "Critical",
            "High",
            "Medium",
            "Low",
        }

        for defect_data in defects_data:
            if not isinstance(defect_data, dict):
                raise ValueError(
                    "Invalid QA defect."
                )

            defect_id = defect_data.get("id")
            title = defect_data.get("title")
            severity = defect_data.get("severity")
            related_story = defect_data.get(
                "related_story"
            )
            expected = defect_data.get("expected")
            actual = defect_data.get("actual")

            string_fields = {
                "id": defect_id,
                "title": title,
                "related_story": related_story,
                "expected": expected,
                "actual": actual,
            }

            for field_name, value in string_fields.items():
                if (
                    not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"QA defect {field_name} is required."
                    )

            if severity not in valid_severities:
                raise ValueError(
                    f"Invalid QA defect severity: {severity}"
                )

            defects.append(
                QADefect(
                    id=defect_id,
                    title=title,
                    severity=severity,
                    related_story=related_story,
                    expected=expected,
                    actual=actual,
                )
            )

        return QAResult(
            summary=summary,
            passed=passed,
            defects=defects,
            test_commands=test_commands,
            blockers=blockers,
        )

    @parses_provider_result("security_result")
    def _parse_security_result(
        self,
        raw_output: str,
    ) -> SecurityResult:
        """Parse a structured security result."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned invalid security JSON."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "Security result must be an object."
            )

        summary = data.get("summary")
        passed = data.get("passed")
        findings_data = data.get("findings", [])
        test_commands = data.get("test_commands", [])
        blockers = data.get("blockers", [])

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "Security result summary is required."
            )

        if not isinstance(passed, bool):
            raise ValueError(
                "Security result passed must be a boolean."
            )

        if not isinstance(findings_data, list):
            raise ValueError(
                "Security result findings must be a list."
            )

        if not isinstance(test_commands, list) or not all(
            isinstance(command, str)
            for command in test_commands
        ):
            raise ValueError(
                "Security result test_commands must be a list of strings."
            )

        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str)
            for blocker in blockers
        ):
            raise ValueError(
                "Security result blockers must be a list of strings."
            )

        valid_severities = {
            "Critical",
            "High",
            "Medium",
            "Low",
            "Informational",
        }

        findings: list[SecurityFinding] = []

        for finding_data in findings_data:
            if not isinstance(finding_data, dict):
                raise ValueError(
                    "Invalid security finding."
                )

            finding_id = finding_data.get("id")
            title = finding_data.get("title")
            severity = finding_data.get("severity")
            affected_component = finding_data.get(
                "affected_component"
            )
            description = finding_data.get("description")
            impact = finding_data.get("impact")
            evidence = finding_data.get("evidence")
            recommended_remediation = finding_data.get(
                "recommended_remediation"
            )
            priority = finding_data.get("priority")
            status = finding_data.get("status")

            string_fields = {
                "id": finding_id,
                "title": title,
                "affected_component": affected_component,
                "description": description,
                "impact": impact,
                "evidence": evidence,
                "recommended_remediation": recommended_remediation,
                "priority": priority,
                "status": status,
            }

            for field_name, value in string_fields.items():
                if (
                    not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"Security finding {field_name} is required."
                    )

            if severity not in valid_severities:
                raise ValueError(
                    f"Invalid security finding severity: {severity}"
                )

            findings.append(
                SecurityFinding(
                    id=finding_id,
                    title=title,
                    severity=severity,
                    affected_component=affected_component,
                    description=description,
                    impact=impact,
                    evidence=evidence,
                    recommended_remediation=recommended_remediation,
                    priority=priority,
                    status=status,
                )
            )

        return SecurityResult(
            summary=summary,
            passed=passed,
            findings=findings,
            test_commands=test_commands,
            blockers=blockers,
        )

    @parses_provider_result("devops_result")
    def _parse_devops_result(
        self,
        raw_output: str,
    ) -> DevOpsResult:
        """Parse a structured DevOps result."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned invalid DevOps JSON."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "DevOps result must be an object."
            )

        summary = data.get("summary")
        passed = data.get("passed")
        changes_data = data.get("changes", [])
        test_commands = data.get(
            "test_commands",
            [],
        )
        blockers = data.get(
            "blockers",
            [],
        )
        deployment_ready = data.get(
            "deployment_ready"
        )
        rollback_strategy = data.get(
            "rollback_strategy"
        )

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "DevOps result summary is required."
            )

        if not isinstance(passed, bool):
            raise ValueError(
                "DevOps result passed must be a boolean."
            )

        if not isinstance(changes_data, list):
            raise ValueError(
                "DevOps result changes must be a list."
            )

        if not isinstance(test_commands, list) or not all(
            isinstance(command, str)
            for command in test_commands
        ):
            raise ValueError(
                "DevOps result test_commands must be a list of strings."
            )

        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str)
            for blocker in blockers
        ):
            raise ValueError(
                "DevOps result blockers must be a list of strings."
            )

        if not isinstance(deployment_ready, bool):
            raise ValueError(
                "DevOps result deployment_ready must be a boolean."
            )

        if not isinstance(
            rollback_strategy,
            str,
        ):
            raise ValueError(
                "DevOps result rollback_strategy must be a string."
            )

        changes: list[DevOpsChange] = []

        for change_data in changes_data:
            if not isinstance(change_data, dict):
                raise ValueError(
                    "Invalid DevOps change."
                )

            path = change_data.get("path")
            description = change_data.get(
                "description"
            )
            category = change_data.get(
                "category"
            )

            string_fields = {
                "path": path,
                "description": description,
                "category": category,
            }

            for field_name, value in string_fields.items():
                if (
                    not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"DevOps change {field_name} is required."
                    )

            changes.append(
                DevOpsChange(
                    path=path,
                    description=description,
                    category=category,
                )
            )

        return DevOpsResult(
            summary=summary,
            passed=passed,
            changes=changes,
            test_commands=test_commands,
            blockers=blockers,
            deployment_ready=deployment_ready,
            rollback_strategy=rollback_strategy,
        )

    @parses_provider_result("sre_result")
    def _parse_sre_result(
        self,
        raw_output: str,
    ) -> SREResult:
        """Parse a structured SRE result."""

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI returned invalid SRE JSON."
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "SRE result must be an object."
            )

        summary = data.get("summary")
        passed = data.get("passed")
        findings_data = data.get("findings", [])
        test_commands = data.get(
            "test_commands",
            [],
        )
        blockers = data.get(
            "blockers",
            [],
        )
        observability_ready = data.get(
            "observability_ready"
        )
        incident_readiness = data.get(
            "incident_readiness"
        )

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "SRE result summary is required."
            )

        if not isinstance(passed, bool):
            raise ValueError(
                "SRE result passed must be a boolean."
            )

        if not isinstance(findings_data, list):
            raise ValueError(
                "SRE result findings must be a list."
            )

        if not isinstance(test_commands, list) or not all(
            isinstance(command, str)
            for command in test_commands
        ):
            raise ValueError(
                "SRE result test_commands must be a list of strings."
            )

        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str)
            for blocker in blockers
        ):
            raise ValueError(
                "SRE result blockers must be a list of strings."
            )

        if not isinstance(observability_ready, bool):
            raise ValueError(
                "SRE result observability_ready must be a boolean."
            )

        if not isinstance(incident_readiness, bool):
            raise ValueError(
                "SRE result incident_readiness must be a boolean."
            )

        valid_severities = {
            "Critical",
            "High",
            "Medium",
            "Low",
            "Informational",
        }

        findings: list[SREFinding] = []

        for finding_data in findings_data:
            if not isinstance(finding_data, dict):
                raise ValueError(
                    "Invalid SRE finding."
                )

            finding_id = finding_data.get("id")
            title = finding_data.get("title")
            severity = finding_data.get("severity")
            category = finding_data.get("category")
            description = finding_data.get(
                "description"
            )
            recommendation = finding_data.get(
                "recommendation"
            )
            status = finding_data.get("status")

            string_fields = {
                "id": finding_id,
                "title": title,
                "category": category,
                "description": description,
                "recommendation": recommendation,
                "status": status,
            }

            for field_name, value in string_fields.items():
                if (
                    not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"SRE finding {field_name} is required."
                    )

            if severity not in valid_severities:
                raise ValueError(
                    f"Invalid SRE finding severity: {severity}"
                )

            findings.append(
                SREFinding(
                    id=finding_id,
                    title=title,
                    severity=severity,
                    category=category,
                    description=description,
                    recommendation=recommendation,
                    status=status,
                )
            )

        return SREResult(
            summary=summary,
            passed=passed,
            findings=findings,
            test_commands=test_commands,
            blockers=blockers,
            observability_ready=observability_ready,
            incident_readiness=incident_readiness,
        )
