from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import load_state


def run_cli(
    monkeypatch,
    capsys,
    *args: str,
) -> str:
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            *args,
        ],
    )

    main()

    return capsys.readouterr().out


def test_cli_run_workflow_full_mock_project_reaches_completed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    output = run_cli(
        monkeypatch,
        capsys,
        "init",
        "CLI E2E App",
    )

    assert "Project created:" in output

    project_root = (
        tmp_path
        / "cli-e2e-app"
    )

    monkeypatch.chdir(
        project_root
    )

    # Product
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: product" in output
    assert (
        "Agent 'product' is waiting for human review."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "product_scope",
    )

    # UX/UI
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: ux_ui" in output
    assert (
        "UX/UI is waiting for Design Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "design",
    )

    # Architect
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: architect" in output
    assert (
        "Architect is waiting for Technology Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "technology",
        "approve",
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "architecture",
    )

    # Developer
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: developer" in output
    assert (
        "Developer is waiting for Development Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "development",
    )

    # QA
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: qa" in output
    assert (
        "QA is waiting for QA Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "qa",
    )

    # Security
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: security" in output
    assert (
        "Security is waiting for Security Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "security",
    )

    # DevOps
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: devops" in output
    assert (
        "DevOps is waiting for DevOps Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "devops",
    )

    # SRE
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert "Agent: sre" in output
    assert (
        "SRE is waiting for SRE Gate completion."
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "sre",
    )

    # Production Gate
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert (
        "Production deployment is waiting for "
        "Production Gate completion."
        in output
    )

    assert (
        "Production Gate status: READY_FOR_REVIEW"
        in output
    )

    run_cli(
        monkeypatch,
        capsys,
        "approve",
        "production_deployment",
    )

    # Completed project
    output = run_cli(
        monkeypatch,
        capsys,
        "run-workflow",
    )

    assert (
        "Project workflow is completed."
        in output
    )

    state = load_state(
        project_root
        / ".factory"
        / "state.yaml"
    )

    assert (
        state["project"]["phase"]
        == "completed"
    )

    assert (
        state["production_gate"]["status"]
        == "APPROVED"
    )

    assert (
        state["production_gate"][
            "human_approval"
        ]
        is True
    )

    assert (
        state["approvals"][
            "production_deployment"
        ]
        is True
    )

    for agent in state[
        "agents"
    ].values():
        assert (
            agent["status"]
            == "APPROVED"
        )