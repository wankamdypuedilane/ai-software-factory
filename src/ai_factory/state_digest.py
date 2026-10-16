"""The part of the workflow state an agent prompt actually needs.

The full state was sent with every agent call, every artifact and every
implementation task. On a real project it had grown to about 20,000 tokens
(retry histories, test logs of tasks long fixed, automatic diagnoses,
owner-facing summaries and question cards), so most of each paid request
repeated it. The digest keeps the workflow position of every agent and, for
the agent at work, what it needs to continue: its plan, what it already
implemented, and the output of the tests that still fail.
"""

from __future__ import annotations

from typing import Any


MAX_SUMMARY_CHARS = 600
MAX_PURPOSE_CHARS = 300
MAX_TEST_OUTPUT_CHARS = 2000

# Facts about the past that the workflow keeps but no agent reasons about.
DROPPED_AGENT_FIELDS = {
    "replan_budget_resets",
    "auto_diagnoses",
    "rework_history",
}

# Owner-facing presentation of a result, rebuilt by every agent run.
DROPPED_RESULT_FIELDS = {
    "owner_summary",
    "question_details",
    "artifacts",
}


def _cut(text: Any, limit: int) -> str:
    text = str(text or "").strip()

    if len(text) <= limit:
        return text

    head = int(limit * 0.4)
    return f"{text[:head]} […] {text[-(limit - head):]}"


def _digest_result(result: dict[str, Any]) -> dict[str, Any]:
    digest: dict[str, Any] = {}

    for key, value in result.items():
        if key in DROPPED_RESULT_FIELDS:
            continue

        if key == "summary":
            digest[key] = _cut(value, MAX_SUMMARY_CHARS)
        elif key == "implementation_results" and isinstance(value, list):
            digest[key] = [
                {
                    "task_id": item.get("task_id"),
                    "summary": _cut(item.get("summary"), MAX_SUMMARY_CHARS // 2),
                    "files": item.get("files", []),
                }
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "implementation_requests" and isinstance(value, list):
            digest[key] = [
                {
                    **{k: v for k, v in item.items() if k != "purpose"},
                    "purpose": _cut(item.get("purpose"), MAX_PURPOSE_CHARS),
                }
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "test_results" and isinstance(value, list):
            digest[key] = [
                {
                    "command": item.get("command"),
                    "returncode": item.get("returncode"),
                    "passed": item.get("passed"),
                    **(
                        {
                            "stdout": _cut(item.get("stdout"), MAX_TEST_OUTPUT_CHARS),
                            "stderr": _cut(item.get("stderr"), MAX_TEST_OUTPUT_CHARS // 2),
                        }
                        if item.get("returncode")
                        else {}
                    ),
                }
                for item in value
                if isinstance(item, dict)
            ]
        else:
            digest[key] = value

    return digest


def digest_state(state: dict[str, Any], agent_name: str | None) -> dict[str, Any]:
    """Return the state an agent prompt needs; never modifies `state`."""

    digest = {key: value for key, value in state.items() if key != "agents"}
    agents: dict[str, Any] = {}

    for name, agent in (state.get("agents") or {}).items():
        if not isinstance(agent, dict):
            agents[name] = agent
            continue

        result = agent.get("last_result") or {}

        if name == agent_name:
            entry = {k: v for k, v in agent.items() if k not in DROPPED_AGENT_FIELDS and k != "last_result"}
            entry["last_result"] = _digest_result(result) if isinstance(result, dict) else result
        else:
            entry = {"status": agent.get("status")}

            if isinstance(result, dict) and result.get("summary"):
                entry["summary"] = _cut(result.get("summary"), MAX_SUMMARY_CHARS)

        agents[name] = entry

    digest["agents"] = agents
    return digest
