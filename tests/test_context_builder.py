from pathlib import Path

from ai_factory.context_builder import (
    build_agent_context,
    is_artifact_relevant_to_agent,
    load_upstream_generated_artifacts,
    trim_artifact_content,
)
from ai_factory.state import save_state


def test_build_agent_context_returns_required_data(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "recommend",
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="architect",
    )

    assert context["agent_name"] == "architect"
    assert isinstance(context["contract"], str)
    assert context["contract"].strip() != ""
    assert context["project"]["project"]["name"] == "Test Project"
    assert context["state"]["agents"]["architect"]["status"] == "READY"


def test_build_agent_context_loads_configured_artifacts(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    artifact_path = tmp_path / "knowledge" / "requirements.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "# Requirements\n\nTest requirement.",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "recommend",
            },
            "context": {
                "agents": {
                    "architect": [
                        "knowledge/requirements.md",
                    ]
                }
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="architect",
    )

    assert "knowledge/requirements.md" in context["artifacts"]
    assert "Test requirement." in context["artifacts"][
        "knowledge/requirements.md"
    ]


def test_build_agent_context_rejects_missing_artifact(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "architect": [
                        "knowledge/missing.md",
                    ]
                }
            },
        },
    )

    try:
        build_agent_context(
            project_root=tmp_path,
            agent_name="architect",
        )

        assert False, "Expected FileNotFoundError"

    except FileNotFoundError:
        pass


def test_build_agent_context_loads_human_input(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    input_path = (
        tmp_path
        / "knowledge"
        / "inputs"
        / "product.md"
    )

    input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path.write_text(
        "# Product Input\n\nBuild a ride-hailing application.",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "product": [],
                }
            },
            "inputs": {
                "directory": "knowledge/inputs",
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="product",
    )

    assert context["human_input"] is not None
    assert "Build a ride-hailing application." in context[
        "human_input"
    ]


def test_build_agent_context_returns_none_without_human_input(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "product": [],
                }
            },
            "inputs": {
                "directory": "knowledge/inputs",
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="product",
    )

    assert context["human_input"] is None


def test_load_upstream_generated_artifacts_loads_previous_agent_files(
    tmp_path: Path,
) -> None:
    vision_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "vision.md"
    )

    requirements_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "requirements.md"
    )

    vision_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    vision_path.write_text(
        "# Vision\n\nRide-hailing product.",
        encoding="utf-8",
    )

    requirements_path.write_text(
        "# Requirements\n\nMVP requirements.",
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
                "last_result": {
                    "generated_artifacts": [
                        "knowledge/project/vision.md",
                        "knowledge/project/requirements.md",
                    ]
                },
            },
            "ux_ui": {
                "status": "READY",
            },
        }
    }

    artifacts = load_upstream_generated_artifacts(
        project_root=tmp_path,
        state=state,
        agent_name="ux_ui",
    )

    assert "knowledge/project/vision.md" in artifacts
    assert "Ride-hailing product." in artifacts[
        "knowledge/project/vision.md"
    ]

    assert "knowledge/project/requirements.md" in artifacts
    assert "MVP requirements." in artifacts[
        "knowledge/project/requirements.md"
    ]


def test_load_upstream_generated_artifacts_ignores_future_agents(
    tmp_path: Path,
) -> None:
    future_path = (
        tmp_path
        / "knowledge"
        / "architecture"
        / "system.md"
    )

    future_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    future_path.write_text(
        "# Architecture",
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "READY",
            },
            "architect": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "generated_artifacts": [
                        "knowledge/architecture/system.md",
                    ]
                },
            },
        }
    }

    artifacts = load_upstream_generated_artifacts(
        project_root=tmp_path,
        state=state,
        agent_name="ux_ui",
    )

    assert artifacts == {}


def test_build_agent_context_includes_upstream_generated_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vision_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "vision.md"
    )

    vision_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    vision_path.write_text(
        "# Product Vision\n\nRide-hailing MVP.",
        encoding="utf-8",
    )

    save_state(
        tmp_path / ".factory" / "state.yaml",
        {
            "agents": {
                "product": {
                    "status": "APPROVED",
                    "last_result": {
                        "generated_artifacts": [
                            "knowledge/project/vision.md",
                        ]
                    },
                },
                "ux_ui": {
                    "status": "READY",
                },
            }
        },
    )

    save_state(
        tmp_path / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "ux_ui": [],
                }
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="ux_ui",
    )

    assert "knowledge/project/vision.md" in context["artifacts"]
    assert (
        "Ride-hailing MVP."
        in context["artifacts"]["knowledge/project/vision.md"]
    )


def test_trim_artifact_content_keeps_short_content() -> None:
    content = "Short artifact content."

    result = trim_artifact_content(
        content,
        max_chars=100,
    )

    assert result == content


def test_trim_artifact_content_truncates_long_content() -> None:
    content = "A" * 200

    result = trim_artifact_content(
        content,
        max_chars=100,
    )

    assert result.startswith("A" * 100)
    assert (
        "[Artifact content truncated for execution context]"
        in result
    )
    assert len(result) < len(content)


def test_upstream_artifacts_are_trimmed(
    tmp_path: Path,
) -> None:
    artifact_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "large.md"
    )

    artifact_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact_path.write_text(
        "A" * 10_000,
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
                "last_result": {
                    "generated_artifacts": [
                        "knowledge/project/large.md",
                    ]
                },
            },
            "ux_ui": {
                "status": "READY",
            },
        }
    }

    artifacts = load_upstream_generated_artifacts(
        project_root=tmp_path,
        state=state,
        agent_name="ux_ui",
    )

    content = artifacts[
        "knowledge/project/large.md"
    ]

    assert len(content) < 10_000
    assert (
        "[Artifact content truncated for execution context]"
        in content
    )


def test_artifact_relevance_for_architect() -> None:
    assert is_artifact_relevant_to_agent(
        "knowledge/project/requirements.md",
        "architect",
    )
    assert is_artifact_relevant_to_agent(
        "design/ux-ui/screen-specs.md",
        "architect",
    )
    assert not is_artifact_relevant_to_agent(
        "knowledge/architecture/api.md",
        "architect",
    )


def test_artifact_relevance_for_qa() -> None:
    assert is_artifact_relevant_to_agent(
        "knowledge/project/requirements.md",
        "qa",
    )
    assert is_artifact_relevant_to_agent(
        "workflows/backlog/user-stories.md",
        "qa",
    )
    assert is_artifact_relevant_to_agent(
        "design/ux-ui/screen-specs.md",
        "qa",
    )
    assert is_artifact_relevant_to_agent(
        "knowledge/architecture/api.md",
        "qa",
    )

    assert not is_artifact_relevant_to_agent(
        "design/ux-ui/design-system.md",
        "qa",
    )


def test_load_upstream_generated_artifacts_filters_irrelevant_files(
    tmp_path: Path,
) -> None:
    requirements = (
        tmp_path
        / "knowledge"
        / "project"
        / "requirements.md"
    )
    design_system = (
        tmp_path
        / "design"
        / "ux-ui"
        / "design-system.md"
    )

    requirements.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    design_system.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    requirements.write_text(
        "Requirements",
        encoding="utf-8",
    )
    design_system.write_text(
        "Design system",
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
                "last_result": {
                    "generated_artifacts": [
                        "knowledge/project/requirements.md",
                    ],
                },
            },
            "ux_ui": {
                "status": "APPROVED",
                "last_result": {
                    "generated_artifacts": [
                        "design/ux-ui/design-system.md",
                    ],
                },
            },
            "architect": {
                "status": "APPROVED",
            },
            "developer": {
                "status": "APPROVED",
            },
            "qa": {
                "status": "READY",
            },
        }
    }

    artifacts = load_upstream_generated_artifacts(
        project_root=tmp_path,
        state=state,
        agent_name="qa",
    )

    assert (
        "knowledge/project/requirements.md"
        in artifacts
    )
    assert (
        "design/ux-ui/design-system.md"
        not in artifacts
    )
