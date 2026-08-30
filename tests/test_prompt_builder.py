from ai_factory.prompt_builder import build_agent_prompt


def test_build_agent_prompt_contains_core_sections() -> None:
    context = {
        "agent_name": "architect",
        "contract": "# Architect Agent\nDefine the architecture.",
        "project": {
            "project": {
                "name": "Test Project",
            }
        },
        "state": {
            "agents": {
                "architect": {
                    "status": "READY",
                }
            }
        },
        "artifacts": {},
    }

    prompt = build_agent_prompt(context)

    assert "# AI Software Factory Agent Execution" in prompt
    assert "Agent: architect" in prompt
    assert "## Agent Contract" in prompt
    assert "Define the architecture." in prompt
    assert "## Project Configuration" in prompt
    assert "Test Project" in prompt
    assert "## Workflow State" in prompt
    assert '"status": "READY"' in prompt
    assert "## Execution Instruction" in prompt


def test_build_agent_prompt_includes_artifacts() -> None:
    context = {
        "agent_name": "architect",
        "contract": "Architect contract",
        "project": {},
        "state": {},
        "artifacts": {
            "knowledge/requirements.md": (
                "# Requirements\n\nSystem requirement."
            ),
            "knowledge/design.md": (
                "# Design\n\nDesign decision."
            ),
        },
    }

    prompt = build_agent_prompt(context)

    assert "## Context Artifacts" in prompt
    assert "### knowledge/requirements.md" in prompt
    assert "System requirement." in prompt
    assert "### knowledge/design.md" in prompt
    assert "Design decision." in prompt


def test_build_agent_prompt_omits_artifact_section_when_empty() -> None:
    context = {
        "agent_name": "architect",
        "contract": "Architect contract",
        "project": {},
        "state": {},
        "artifacts": {},
    }

    prompt = build_agent_prompt(context)

    assert "## Context Artifacts" not in prompt


def test_build_agent_prompt_includes_human_input() -> None:
    context = {
        "agent_name": "product",
        "contract": "Product contract",
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": (
            "# Product Input\n\n"
            "Build a ride-hailing application for students."
        ),
    }

    prompt = build_agent_prompt(context)

    assert "## Human Input" in prompt
    assert (
        "Build a ride-hailing application for students."
        in prompt
    )


def test_build_agent_prompt_omits_human_input_when_missing() -> None:
    context = {
        "agent_name": "product",
        "contract": "Product contract",
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": None,
    }

    prompt = build_agent_prompt(context)

    assert "## Human Input" not in prompt


def test_build_agent_prompt_includes_developer_specific_instruction() -> None:
    context = {
        "agent_name": "developer",
        "contract": "Developer contract",
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": None,
    }

    prompt = build_agent_prompt(context)

    assert "## Agent-Specific Instruction" in prompt
    assert "implementation_requests" in prompt
    assert "Do not generate the entire application implementation" in prompt


def test_build_agent_prompt_omits_agent_specific_instruction_for_other_agents() -> None:
    context = {
        "agent_name": "qa",
        "contract": "QA contract",
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": None,
    }

    prompt = build_agent_prompt(context)

    assert "## Agent-Specific Instruction" not in prompt
