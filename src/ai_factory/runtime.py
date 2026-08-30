from pathlib import Path

from ai_factory.agent_runner import run_agent
from ai_factory.artifact_runtime import run_artifact_generation
from ai_factory.context_builder import build_agent_context
from ai_factory.design_gate_runtime import (
    update_design_gate_from_result,
)
from ai_factory.implementation_batch import (
    run_implementation_batch,
)
from ai_factory.orchestrator import (
    get_execution_blocker,
    get_next_agent,
)
from ai_factory.providers import ModelProvider
from ai_factory.result_application import apply_agent_result
from ai_factory.state import load_state, save_state
from ai_factory.technology_runtime import (
    update_technology_gate_from_architect_result,
)


def run_next_agent(
    project_root: Path,
    provider: ModelProvider,
) -> tuple[str, str]:
    """Determine and execute the next agent in the project workflow."""

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    agent_name = get_next_agent(state)

    if agent_name is None:
        blocker = get_execution_blocker(state)

        if blocker:
            raise ValueError(
                "Execution blocked.\n"
                f"{blocker}"
            )

        raise ValueError(
            "No agent is currently ready for execution."
        )

    result = run_agent(
        project_root=project_root,
        agent_name=agent_name,
        provider=provider,
    )

    context = build_agent_context(
        project_root=project_root,
        agent_name=agent_name,
    )
    config = context["project"]

    implementation_batch = None

    if agent_name == "developer":
        implementation_batch = run_implementation_batch(
            project_root=project_root,
            agent_name=agent_name,
            agent_result=result,
            context=context,
            provider=provider,
        )

    generated_artifacts = run_artifact_generation(
        project_root=project_root,
        agent_name=agent_name,
        result=result,
        context=context,
        provider=provider,
    )

    generated_paths = [
        artifact.path
        for artifact in generated_artifacts
    ]

    state = apply_agent_result(
        state,
        agent_name,
        result,
    )

    if implementation_batch is not None:
        developer_result = state["agents"][agent_name]["last_result"]

        developer_result["implementation_results"] = [
            {
                "task_id": item.task_id,
                "summary": item.summary,
                "tests": list(item.tests),
                "blockers": list(item.blockers),
                "files": [
                    change.path
                    for change in item.files
                ],
            }
            for item in implementation_batch.results
        ]

        developer_result["implemented_files"] = [
            path.relative_to(project_root).as_posix()
            for path in implementation_batch.written_files
        ]

        developer_result["implementation_blocked"] = (
            implementation_batch.blocked
        )

        developer_result["implementation_blockers"] = [
            {
                "task_id": item.task_id,
                "blockers": list(item.blockers),
            }
            for item in implementation_batch.results
            if item.blockers
        ]

        if implementation_batch.blocked:
            state["agents"][agent_name]["status"] = "BLOCKED"

    if generated_paths:
        state["agents"][agent_name]["last_result"][
            "generated_artifacts"
        ] = generated_paths

    if agent_name == "ux_ui":
        state = update_design_gate_from_result(
            state=state,
            result=result,
            generated_paths=generated_paths,
        )

    if agent_name == "architect":
        state = update_technology_gate_from_architect_result(
            state=state,
            config=config,
            result=result,
        )

    save_state(
        state_path,
        state,
    )

    return agent_name, result
