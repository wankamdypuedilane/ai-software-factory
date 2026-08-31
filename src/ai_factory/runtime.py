from pathlib import Path

from ai_factory.agent_runner import run_agent
from ai_factory.artifact_runtime import run_artifact_generation
from ai_factory.context_builder import build_agent_context
from ai_factory.design_gate_runtime import (
    update_design_gate_from_result,
)
from ai_factory.development_gate_runtime import (
    update_development_gate_from_state,
)
from ai_factory.implementation_batch import (
    run_implementation_batch,
)
from ai_factory.implementation_history import (
    merge_implementation_results,
)
from ai_factory.implementation_resume import (
    get_completed_implementation_task_ids,
)
from ai_factory.implementation_retry import (
    build_implementation_retry_context,
)
from ai_factory.orchestrator import (
    get_execution_blocker,
    get_next_agent,
)
from ai_factory.providers import (
    ModelProvider,
    QAProvider,
    SecurityProvider,
)
from ai_factory.qa_gate_runtime import (
    update_qa_gate_from_state,
)
from ai_factory.result_application import apply_agent_result
from ai_factory.qa_runtime import run_qa_validation
from ai_factory.security_runtime import (
    run_security_validation,
)
from ai_factory.security_gate_runtime import (
    update_security_gate_from_state,
)
from ai_factory.state import load_state, save_state
from ai_factory.test_result_serialization import (
    serialize_test_results,
)
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

    developer_retry_context = None

    developer_state = state.get(
        "agents",
        {},
    ).get(
        "developer",
    )

    if isinstance(developer_state, dict):
        developer_last_result = developer_state.get(
            "last_result",
            {},
        )

        if isinstance(developer_last_result, dict):
            failed_task_id = developer_last_result.get(
                "failed_task_id"
            )

            test_results = developer_last_result.get(
                "test_results",
                [],
            )

            has_failed_tests = (
                isinstance(test_results, list)
                and any(
                    isinstance(item, dict)
                    and item.get("passed") is False
                    for item in test_results
                )
            )

            if (
                isinstance(failed_task_id, str)
                and failed_task_id.strip()
                and has_failed_tests
            ):
                developer_retry_context = (
                    build_implementation_retry_context(
                        state
                    )
                )

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

    qa_execution = None
    security_execution = None

    if agent_name == "qa":
        if not isinstance(
            provider,
            QAProvider,
        ):
            raise ValueError(
                "QA execution requires a QA-capable provider."
            )

        developer_state = state.get(
            "agents",
            {},
        ).get(
            "developer",
            {},
        )

        developer_result = {}

        if isinstance(
            developer_state,
            dict,
        ):
            stored_result = developer_state.get(
                "last_result",
                {},
            )

            if isinstance(
                stored_result,
                dict,
            ):
                developer_result = stored_result

        qa_context = dict(context)
        qa_context["developer"] = developer_result

        qa_execution = run_qa_validation(
            project_root=project_root,
            context=qa_context,
            provider=provider,
        )

    if agent_name == "security":
        if not isinstance(
            provider,
            SecurityProvider,
        ):
            raise ValueError(
                "Security execution requires a "
                "Security-capable provider."
            )

        agents = state.get(
            "agents",
            {},
        )

        developer_result = {}
        qa_result = {}

        if isinstance(agents, dict):
            developer_state = agents.get(
                "developer",
                {},
            )

            if isinstance(developer_state, dict):
                stored_developer_result = (
                    developer_state.get(
                        "last_result",
                        {},
                    )
                )

                if isinstance(
                    stored_developer_result,
                    dict,
                ):
                    developer_result = (
                        stored_developer_result
                    )

            qa_state = agents.get(
                "qa",
                {},
            )

            if isinstance(qa_state, dict):
                stored_qa_result = qa_state.get(
                    "last_result",
                    {},
                )

                if isinstance(
                    stored_qa_result,
                    dict,
                ):
                    qa_result = stored_qa_result

        security_context = dict(context)
        security_context["developer"] = (
            developer_result
        )
        security_context["qa"] = qa_result

        security_execution = (
            run_security_validation(
                project_root=project_root,
                context=security_context,
                provider=provider,
            )
        )

    implementation_batch = None

    if agent_name == "developer":
        completed_task_ids = (
            get_completed_implementation_task_ids(
                state
            )
        )

        retry_task_id = None
        retry_test_results = None

        if developer_retry_context is not None:
            retry_task_id = (
                developer_retry_context.task.id
            )
            retry_test_results = (
                developer_retry_context.test_results
            )

        implementation_batch = run_implementation_batch(
            project_root=project_root,
            agent_name=agent_name,
            agent_result=result,
            context=context,
            provider=provider,
            completed_task_ids=completed_task_ids,
            retry_task_id=retry_task_id,
            retry_test_results=retry_test_results,
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

    previous_implementation_results = []
    previous_implemented_files = []

    if agent_name == "developer":
        previous_developer_state = state["agents"].get(
            "developer",
            {},
        )

        if isinstance(previous_developer_state, dict):
            previous_last_result = previous_developer_state.get(
                "last_result",
                {},
            )

            if isinstance(previous_last_result, dict):
                stored_results = previous_last_result.get(
                    "implementation_results",
                    [],
                )

                if isinstance(stored_results, list):
                    previous_implementation_results = list(
                        stored_results
                    )

                stored_files = previous_last_result.get(
                    "implemented_files",
                    [],
                )

                if isinstance(stored_files, list):
                    previous_implemented_files = [
                        path
                        for path in stored_files
                        if isinstance(path, str)
                    ]

    state = apply_agent_result(
        state,
        agent_name,
        result,
    )

    if qa_execution is not None:
        qa_state = state["agents"][agent_name]
        qa_last_result = qa_state["last_result"]

        qa_result = qa_execution.result

        qa_last_result["qa_summary"] = (
            qa_result.summary
        )

        qa_last_result["qa_model_passed"] = (
            qa_result.passed
        )

        qa_last_result["qa_passed"] = (
            qa_execution.passed
        )

        qa_last_result["qa_defects"] = [
            {
                "id": defect.id,
                "title": defect.title,
                "severity": defect.severity,
                "related_story": defect.related_story,
                "expected": defect.expected,
                "actual": defect.actual,
            }
            for defect in qa_result.defects
        ]

        qa_last_result["qa_blockers"] = list(
            qa_result.blockers
        )

        qa_last_result["qa_test_results"] = (
            serialize_test_results(
                qa_execution.test_results
            )
        )

        if qa_result.blockers:
            qa_state["status"] = "BLOCKED"

        elif not qa_execution.passed:
            qa_state["status"] = "FAILED"

        else:
            qa_state["status"] = "REVIEW_REQUIRED"

        if isinstance(
            state.get("qa_gate"),
            dict,
        ):
            state = update_qa_gate_from_state(
                state
            )

    if security_execution is not None:
        security_state = state["agents"][agent_name]
        security_last_result = security_state[
            "last_result"
        ]

        security_result = security_execution.result

        security_last_result["security_summary"] = (
            security_result.summary
        )

        security_last_result[
            "security_model_passed"
        ] = security_result.passed

        security_last_result["security_passed"] = (
            security_execution.passed
        )

        security_last_result["security_findings"] = [
            {
                "id": finding.id,
                "title": finding.title,
                "severity": finding.severity,
                "affected_component": (
                    finding.affected_component
                ),
                "description": finding.description,
                "impact": finding.impact,
                "evidence": finding.evidence,
                "recommended_remediation": (
                    finding.recommended_remediation
                ),
                "priority": finding.priority,
                "status": finding.status,
            }
            for finding in security_result.findings
        ]

        security_last_result["security_blockers"] = list(
            security_result.blockers
        )

        security_last_result[
            "security_test_results"
        ] = serialize_test_results(
            security_execution.test_results
        )

        if security_result.blockers:
            security_state["status"] = "BLOCKED"

        elif not security_execution.passed:
            security_state["status"] = "FAILED"

        else:
            security_state["status"] = "REVIEW_REQUIRED"

        if isinstance(
            state.get("security_gate"),
            dict,
        ):
            state = update_security_gate_from_state(
                state
            )

    if implementation_batch is not None:
        developer_result = state["agents"][agent_name]["last_result"]

        new_implementation_results = [
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

        developer_result["implementation_results"] = (
            merge_implementation_results(
                previous_results=previous_implementation_results,
                new_results=new_implementation_results,
            )
        )

        new_implemented_files = [
            path.relative_to(project_root).as_posix()
            for path in implementation_batch.written_files
        ]

        developer_result["implemented_files"] = list(
            dict.fromkeys(
                previous_implemented_files
                + new_implemented_files
            )
        )

        developer_result["implementation_blocked"] = (
            implementation_batch.blocked
        )

        developer_result["implementation_test_failed"] = (
            implementation_batch.test_failed
        )

        developer_result["failed_task_id"] = (
            implementation_batch.failed_task_id
        )

        developer_result["test_results"] = (
            serialize_test_results(
                implementation_batch.test_results
            )
        )

        if (
            not implementation_batch.blocked
            and not implementation_batch.test_failed
        ):
            developer_result["failed_task_id"] = None
            developer_result["implementation_test_failed"] = False

        developer_result["implementation_blockers"] = [
            {
                "task_id": item.task_id,
                "blockers": list(item.blockers),
            }
            for item in implementation_batch.results
            if item.blockers
        ]

        developer_result["resume_from"] = None

        for item in implementation_batch.results:
            if item.blockers:
                developer_result["resume_from"] = item.task_id
                break

        if implementation_batch.blocked:
            state["agents"][agent_name]["status"] = "BLOCKED"

        elif implementation_batch.test_failed:
            state["agents"][agent_name]["status"] = "FAILED"

        if (
            agent_name == "developer"
            and isinstance(
                state.get("development_gate"),
                dict,
            )
        ):
            state = update_development_gate_from_state(
                state
            )

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
