from pathlib import Path

from ai_factory.project import initialize_project
from ai_factory.providers import MockProvider
from ai_factory.resume import resume_agent_with_input
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state


def test_factory_resumes_blocked_product_after_human_input(
    tmp_path: Path,
) -> None:
    project_root = initialize_project(
        project_name="Resume Test App",
        target_dir=tmp_path,
    )

    state_path = (
        project_root
        / ".factory"
        / "state.yaml"
    )

    config_path = (
        project_root
        / ".factory"
        / "project.yaml"
    )

    state = load_state(
        state_path
    )

    config = load_state(
        config_path
    )

    state["agents"]["product"]["status"] = "BLOCKED"

    save_state(
        state_path,
        state,
    )

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["product"]["status"]
        == "BLOCKED"
    )

    assert (
        state["project"]["phase"]
        == "discovery"
    )

    input_directory = config[
        "inputs"
    ]["directory"]

    input_path = (
        project_root
        / input_directory
        / "product.md"
    )

    input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path.write_text(
        (
            "# Product Input\n\n"
            "The application is a simple task manager.\n"
        ),
        encoding="utf-8",
    )

    state = resume_agent_with_input(
        project_root=project_root,
        state=state,
        project_config=config,
        agent_name="product",
    )

    save_state(
        state_path,
        state,
    )

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["product"]["status"]
        == "READY"
    )

    assert (
        state["project"]["phase"]
        == "discovery"
    )

    provider = MockProvider()

    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "product"

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["product"]["status"]
        == "REVIEW_REQUIRED"
    )

    assert (
        state["project"]["phase"]
        == "discovery"
    )