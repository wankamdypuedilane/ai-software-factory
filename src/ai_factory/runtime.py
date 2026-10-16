from pathlib import Path

from ai_factory.auto_diagnosis import try_auto_diagnosis
from ai_factory.project_environment import project_environment
from ai_factory.rework import mark_rework_addressed
from ai_factory.validation_context import (
    add_validation_evidence,
    build_validation_outcome,
)
from ai_factory.agent_result import AgentResult
from ai_factory.agent_runner import run_agent
from ai_factory.artifact_runtime import run_artifact_generation
from ai_factory.context_builder import build_agent_context
from ai_factory.design_gate_runtime import (
    update_design_gate_from_result,
)
from ai_factory.development_gate_runtime import (
    update_development_gate_from_state,
)
from ai_factory.devops_gate_runtime import (
    update_devops_gate_from_state,
)
from ai_factory.devops_runtime import (
    run_devops_validation,
)
from ai_factory.replan_guard import (
    NonConvergingImplementationError,
    assert_replan_budget,
    build_failure_signature,
    get_failure_signature,
    get_repeated_failures,
    get_replan_count,
    next_repeated_failures,
    next_replan_count,
)
from ai_factory.qa_retry_guard import (
    advance_qa_retry_state,
    assert_qa_retry_budget,
    get_qa_failure_signature,
    get_qa_repeated_failures,
    get_qa_retry_count,
)
from ai_factory.security_retry_guard import (
    advance_security_retry_state,
    assert_security_retry_budget,
    get_security_failure_signature,
    get_security_repeated_failures,
    get_security_retry_count,
)
from ai_factory.devops_retry_guard import (
    advance_devops_retry_state,
    assert_devops_retry_budget,
    get_devops_failure_signature,
    get_devops_repeated_failures,
    get_devops_retry_count,
)
from ai_factory.blocker_contract import (
    serialize_blockers,
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
    DevOpsProvider,
    ModelProvider,
    QAProvider,
    SecurityProvider,
    SREProvider,
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
from ai_factory.sre_runtime import (
    run_sre_validation,
)
from ai_factory.sre_gate_runtime import (
    update_sre_gate_from_state,
)
from ai_factory.sre_retry_guard import (
    advance_sre_retry_state,
    assert_sre_retry_budget,
    get_sre_failure_signature,
    get_sre_repeated_failures,
    get_sre_retry_count,
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

    with project_environment(project_root):
        return _run_next_agent(project_root, provider)


def _run_next_agent(
    project_root: Path,
    provider: ModelProvider,
) -> tuple[str, str]:

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

    if agent_name == "developer":
        # Checked before any provider call: an exhausted budget costs
        # nothing, and the persisted diagnostics stay untouched.
        assert_replan_budget(state)

    if agent_name == "qa":
        # Same guarantee for QA, which `get_next_agent` also re-selects
        # after a failure and which had no bound of its own.
        assert_qa_retry_budget(state)

    if agent_name == "security":
        assert_security_retry_budget(state)

    if agent_name == "devops":
        assert_devops_retry_budget(state)

    if agent_name == "sre":
        # The last downstream validation agent `get_next_agent` re-selects
        # after a failure. Checked here, before `run_agent`, so an exhausted
        # budget costs neither an agent run nor an SRE validation call.
        assert_sre_retry_budget(state)

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
    devops_execution = None
    sre_execution = None

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

        qa_context = add_validation_evidence(
            context,
            project_root=project_root,
            developer_result=developer_result,
        )
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

        security_context = add_validation_evidence(
            context,
            project_root=project_root,
            developer_result=developer_result,
        )
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

    if agent_name == "devops":
        if not isinstance(
            provider,
            DevOpsProvider,
        ):
            raise ValueError(
                "DevOps execution requires a "
                "DevOps-capable provider."
            )

        agents = state.get(
            "agents",
            {},
        )

        developer_result = {}
        qa_result = {}
        security_result = {}

        if isinstance(agents, dict):
            developer_state = agents.get(
                "developer",
                {},
            )
            qa_state = agents.get(
                "qa",
                {},
            )
            security_state = agents.get(
                "security",
                {},
            )

            if isinstance(developer_state, dict):
                stored_result = developer_state.get(
                    "last_result",
                    {},
                )

                if isinstance(stored_result, dict):
                    developer_result = stored_result

            if isinstance(qa_state, dict):
                stored_result = qa_state.get(
                    "last_result",
                    {},
                )

                if isinstance(stored_result, dict):
                    qa_result = stored_result

            if isinstance(security_state, dict):
                stored_result = security_state.get(
                    "last_result",
                    {},
                )

                if isinstance(stored_result, dict):
                    security_result = stored_result

        devops_context = add_validation_evidence(
            context,
            project_root=project_root,
            developer_result=developer_result,
        )
        devops_context["developer"] = developer_result
        devops_context["qa"] = qa_result
        devops_context["security"] = security_result

        devops_execution = run_devops_validation(
            project_root=project_root,
            context=devops_context,
            provider=provider,
        )

    if agent_name == "sre":
        if not isinstance(
            provider,
            SREProvider,
        ):
            raise ValueError(
                "SRE execution requires an "
                "SRE-capable provider."
            )

        agents = state.get(
            "agents",
            {},
        )

        developer_result = {}
        qa_result = {}
        security_result = {}
        devops_result = {}

        if isinstance(agents, dict):
            for (
                source_name,
                target_name,
            ) in (
                ("developer", "developer"),
                ("qa", "qa"),
                ("security", "security"),
                ("devops", "devops"),
            ):
                source_state = agents.get(
                    source_name,
                    {},
                )

                if not isinstance(
                    source_state,
                    dict,
                ):
                    continue

                stored_result = source_state.get(
                    "last_result",
                    {},
                )

                if not isinstance(
                    stored_result,
                    dict,
                ):
                    continue

                if target_name == "developer":
                    developer_result = stored_result
                elif target_name == "qa":
                    qa_result = stored_result
                elif target_name == "security":
                    security_result = stored_result
                else:
                    devops_result = stored_result

        sre_context = add_validation_evidence(
            context,
            project_root=project_root,
            developer_result=developer_result,
        )
        sre_context["developer"] = developer_result
        sre_context["qa"] = qa_result
        sre_context["security"] = security_result
        sre_context["devops"] = devops_result

        sre_execution = run_sre_validation(
            project_root=project_root,
            context=sre_context,
            provider=provider,
        )

    implementation_batch = None

    # `apply_agent_result` replaces last_result wholesale, so the previous
    # cycle's history has to be read before it is destroyed. It is the only
    # moment where the previous and the new cycle are both knowable.
    previous_replan_count = get_replan_count(state)
    previous_failure_signature = get_failure_signature(state)
    previous_repeated_failures = get_repeated_failures(state)

    previous_qa_retry_count = get_qa_retry_count(state)
    previous_qa_failure_signature = get_qa_failure_signature(state)
    previous_qa_repeated_failures = get_qa_repeated_failures(state)

    previous_security_retry_count = get_security_retry_count(state)
    previous_security_failure_signature = (
        get_security_failure_signature(state)
    )
    previous_security_repeated_failures = (
        get_security_repeated_failures(state)
    )

    previous_devops_retry_count = get_devops_retry_count(state)
    previous_devops_failure_signature = (
        get_devops_failure_signature(state)
    )
    previous_devops_repeated_failures = (
        get_devops_repeated_failures(state)
    )

    previous_sre_retry_count = get_sre_retry_count(state)
    previous_sre_failure_signature = get_sre_failure_signature(state)
    previous_sre_repeated_failures = get_sre_repeated_failures(state)

    if agent_name == "developer":
        completed_task_ids = (
            get_completed_implementation_task_ids(
                state
            )
        )

        retry_task_id = None
        retry_task = None
        retry_test_results = None

        if developer_retry_context is not None:
            retry_task_id = (
                developer_retry_context.task.id
            )
            retry_task = (
                developer_retry_context.task
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
            retry_task=retry_task,
            retry_test_results=retry_test_results,
        )

    artifact_context = context

    validation_execution = {
        "qa": qa_execution,
        "security": security_execution,
        "devops": devops_execution,
        "sre": sre_execution,
    }.get(agent_name)

    if validation_execution is not None:
        artifact_context = dict(context)
        artifact_context["validation_outcome"] = build_validation_outcome(
            agent_name,
            validation_execution,
        )

    generated_artifacts = run_artifact_generation(
        project_root=project_root,
        agent_name=agent_name,
        result=result,
        context=artifact_context,
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

        qa_last_result["qa_blockers"] = serialize_blockers(
            qa_result.blockers
        )

        qa_last_result["qa_test_results"] = (
            serialize_test_results(
                qa_execution.test_results
            )
        )

        # Recorded before the status is chosen, so a bounded stop keeps the
        # evidence, the defects and the blockers of the cycle that spent the
        # budget. A successful cycle clears the history, so an unrelated
        # future QA run never inherits a stale non-convergence state.
        advance_qa_retry_state(
            qa_last_result,
            previous_count=previous_qa_retry_count,
            previous_signature=previous_qa_failure_signature,
            previous_repeated=previous_qa_repeated_failures,
            cycle_failed=not qa_execution.passed,
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

        security_last_result["security_blockers"] = serialize_blockers(
            security_result.blockers
        )

        security_last_result[
            "security_test_results"
        ] = serialize_test_results(
            security_execution.test_results
        )

        # Recorded before the status is chosen, so a bounded stop keeps the
        # evidence, the findings and the blockers of the cycle that spent
        # the budget. A successful cycle clears the history, so a later
        # unrelated Security run never inherits a stale state.
        advance_security_retry_state(
            security_last_result,
            previous_count=previous_security_retry_count,
            previous_signature=previous_security_failure_signature,
            previous_repeated=previous_security_repeated_failures,
            cycle_failed=not security_execution.passed,
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

    if devops_execution is not None:
        devops_state = state["agents"][agent_name]
        devops_last_result = devops_state[
            "last_result"
        ]

        devops_result = devops_execution.result

        devops_last_result["devops_summary"] = (
            devops_result.summary
        )

        devops_last_result[
            "devops_model_passed"
        ] = devops_result.passed

        devops_last_result["devops_passed"] = (
            devops_execution.passed
        )

        devops_last_result["devops_changes"] = [
            {
                "path": change.path,
                "description": change.description,
                "category": change.category,
            }
            for change in devops_result.changes
        ]

        devops_last_result["devops_blockers"] = serialize_blockers(
            devops_result.blockers
        )

        devops_last_result[
            "devops_test_results"
        ] = serialize_test_results(
            devops_execution.test_results
        )

        devops_last_result["deployment_ready"] = (
            devops_result.deployment_ready
        )

        devops_last_result["rollback_strategy"] = (
            devops_result.rollback_strategy
        )

        # Recorded before the status is chosen, so a bounded stop keeps the
        # evidence, the deployment flag, the rollback strategy and the
        # blockers of the cycle that spent the budget. A successful cycle
        # clears the history.
        advance_devops_retry_state(
            devops_last_result,
            previous_count=previous_devops_retry_count,
            previous_signature=previous_devops_failure_signature,
            previous_repeated=previous_devops_repeated_failures,
            cycle_failed=not devops_execution.passed,
        )

        if devops_result.blockers:
            devops_state["status"] = "BLOCKED"

        elif not devops_execution.passed:
            devops_state["status"] = "FAILED"

        else:
            devops_state["status"] = "REVIEW_REQUIRED"

        if isinstance(
            state.get("devops_gate"),
            dict,
        ):
            state = update_devops_gate_from_state(
                state
            )

    if sre_execution is not None:
        sre_state = state["agents"][agent_name]
        sre_last_result = sre_state[
            "last_result"
        ]

        sre_result = sre_execution.result

        sre_last_result["sre_summary"] = (
            sre_result.summary
        )

        sre_last_result[
            "sre_model_passed"
        ] = sre_result.passed

        sre_last_result["sre_passed"] = (
            sre_execution.passed
        )

        sre_last_result["sre_findings"] = [
            {
                "id": finding.id,
                "title": finding.title,
                "severity": finding.severity,
                "category": finding.category,
                "description": finding.description,
                "recommendation": finding.recommendation,
                "status": finding.status,
            }
            for finding in sre_result.findings
        ]

        sre_last_result["sre_blockers"] = serialize_blockers(
            sre_result.blockers
        )

        sre_last_result[
            "sre_test_results"
        ] = serialize_test_results(
            sre_execution.test_results
        )

        sre_last_result[
            "observability_ready"
        ] = sre_result.observability_ready

        sre_last_result[
            "incident_readiness"
        ] = sre_result.incident_readiness

        # Recorded before the status is chosen, so a bounded stop keeps the
        # evidence, the findings, the blockers and both readiness flags of
        # the cycle that spent the budget. A successful cycle clears the
        # history, so a later independent SRE run never inherits a stale
        # non-convergence state.
        advance_sre_retry_state(
            sre_last_result,
            previous_count=previous_sre_retry_count,
            previous_signature=previous_sre_failure_signature,
            previous_repeated=previous_sre_repeated_failures,
            cycle_failed=not sre_execution.passed,
        )

        if sre_result.blockers:
            sre_state["status"] = "BLOCKED"

        elif not sre_execution.passed:
            sre_state["status"] = "FAILED"

        else:
            sre_state["status"] = "REVIEW_REQUIRED"

        if isinstance(
            state.get("sre_gate"),
            dict,
        ):
            state = update_sre_gate_from_state(
                state
            )

    if implementation_batch is not None:
        developer_result = state["agents"][agent_name]["last_result"]

        new_implementation_results = [
            {
                "task_id": item.task_id,
                "summary": item.summary,
                "tests": list(item.tests),
                "blockers": serialize_blockers(item.blockers),
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
                "blockers": serialize_blockers(item.blockers),
            }
            for item in implementation_batch.results
            if item.blockers
        ]

        cycle_failed = (
            implementation_batch.blocked
            or implementation_batch.test_failed
        )

        new_failure_signature = (
            build_failure_signature(developer_result)
            if cycle_failed
            else ""
        )

        developer_result["replan_count"] = next_replan_count(
            previous_replan_count,
            failed=cycle_failed,
        )

        developer_result["failure_signature"] = new_failure_signature

        # The only place two distinct cycles are both known.
        developer_result["repeated_failures"] = next_repeated_failures(
            previous_repeated_failures,
            previous_failure_signature,
            new_failure_signature,
        )

        developer_result["resume_from"] = None

        for item in implementation_batch.results:
            if item.blockers:
                developer_result["resume_from"] = item.task_id
                break

        if implementation_batch.blocked:
            state["agents"][agent_name]["status"] = "BLOCKED"

        elif implementation_batch.test_failed:
            state["agents"][agent_name]["status"] = "FAILED"

        else:
            state = mark_rework_addressed(state)

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


def run_workflow(
    project_root: Path,
    provider: ModelProvider,
) -> list[tuple[str, AgentResult]]:
    """Run agents until the workflow reaches a human or execution gate."""

    executions: list[tuple[str, AgentResult]] = []

    while True:
        state = load_state(
            project_root / ".factory" / "state.yaml"
        )

        agent_name = get_next_agent(state)

        if agent_name is None:
            break

        try:
            executed_agent, result = run_next_agent(
                project_root=project_root,
                provider=provider,
            )
        except NonConvergingImplementationError:
            # Before handing a stuck Developer to a human, let the Factory
            # diagnose it once more, as an expert would (bounded per task).
            if try_auto_diagnosis(project_root, provider):
                continue

            raise

        executions.append(
            (
                executed_agent,
                result,
            )
        )

    return executions
