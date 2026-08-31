import argparse
from pathlib import Path

from ai_factory.approval_runtime import apply_approval
from ai_factory.design_gate import get_design_gate
from ai_factory.design_gate_runtime import (
    rebuild_design_gate_from_state,
)
from ai_factory.orchestrator import get_next_agent
from ai_factory.project import initialize_project
from ai_factory.provider_factory import create_provider
from ai_factory.result_renderer import render_agent_result
from ai_factory.resume import resume_agent_with_input
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state
from ai_factory.status import (
    get_workflow_gates,
)
from ai_factory.technology_gate import (
    approve_technology_gate,
    is_technology_gate_approved,
    submit_technology_proposal,
)
from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)
from ai_factory.transitions import retry_agent, set_agent_status


def show_status(project_root: Path) -> None:
    """Display the current Factory project status."""

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    project = state["project"]
    agents = state["agents"]

    print(f"Project: {project['name']}")
    print(f"Phase: {project['phase']}")
    print()

    for agent_name, agent_data in agents.items():
        print(f"{agent_name:<12} {agent_data['status']}")

    if "design_gate" in state:
        design_gate = get_design_gate(state)

        groups = design_gate.get("groups", {})
        external_blockers = design_gate.get(
            "external_blockers",
            [],
        )

        approval_status = (
            "approved"
            if design_gate.get("human_approval", False)
            else "pending"
        )

        print()
        print("Design Gate:")
        print(
            f"  Status:            "
            f"{design_gate.get('status', 'UNKNOWN')}"
        )

        for group_name, group_data in groups.items():
            approved = group_data.get("approved", 0)
            total = group_data.get("total", 0)

            print(
                f"  {group_name.capitalize():<18}"
                f"{approved}/{total}"
            )

        if external_blockers:
            print(
                "  External blockers: "
                + ", ".join(external_blockers)
            )
        else:
            print("  External blockers: none")

        print(f"  Human approval:    {approval_status}")

    workflow_gates = get_workflow_gates(
        state
    )

    additional_gates = [
        gate
        for gate in workflow_gates
        if gate["key"] != "design_gate"
    ]

    if additional_gates:
        print()
        print("Workflow Gates:")

        for gate in additional_gates:
            approval_status = (
                "approved"
                if gate["human_approval"]
                else "pending"
            )

            print(
                f"  {gate['name']:<20}"
                f"{gate['status']:<20}"
                f"{approval_status}"
            )

    next_agent = get_next_agent(state)

    print()

    if next_agent:
        print(f"Next agent: {next_agent}")
    else:
        print("Next agent: none")


def main() -> None:
    """Entry point for the AI Software Factory CLI."""

    parser = argparse.ArgumentParser(
        prog="ai-factory",
        description="AI Software Factory command-line interface",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="AI Software Factory 0.1.0",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new Factory project",
    )

    init_parser.add_argument(
        "project_name",
        help="Name of the project to create",
    )

    subparsers.add_parser(
        "status",
        help="Display the current Factory project status",
    )

    subparsers.add_parser(
        "next",
        help="Display the next agent that should work",
    )

    subparsers.add_parser(
        "run",
        help="Execute the next ready agent",
    )

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a blocked agent after human input is provided",
    )

    resume_parser.add_argument(
        "agent_name",
        help="Blocked agent to resume",
    )

    retry_parser = subparsers.add_parser(
        "retry",
        help="Retry a blocked, failed, or review-required agent",
    )

    retry_parser.add_argument(
        "agent_name",
        help="Agent to retry",
    )

    set_status_parser = subparsers.add_parser(
        "set-status",
        help="Update the status of an agent",
    )

    set_status_parser.add_argument(
        "agent_name",
        help="Agent name",
    )

    set_status_parser.add_argument(
        "status",
        help="New agent status",
    )

    approve_parser = subparsers.add_parser(
        "approve",
        help="Record an explicit human approval",
    )

    approve_parser.add_argument(
        "approval_name",
        help="Approval to record",
    )

    design_parser = subparsers.add_parser(
        "design",
    )

    design_subparsers = design_parser.add_subparsers(
        dest="design_command",
    )

    design_subparsers.add_parser(
        "rebuild",
        help="Rebuild the Design Gate from persisted UX/UI results.",
    )

    technology_parser = subparsers.add_parser(
        "technology",
        help="Manage the project technology decision",
    )

    technology_subparsers = technology_parser.add_subparsers(
        dest="technology_command",
        required=True,
    )

    technology_subparsers.add_parser(
        "status",
        help="Display the current Technology Gate status",
    )

    technology_submit_parser = technology_subparsers.add_parser(
        "submit",
        help="Submit a technology proposal for human review",
    )

    technology_submit_parser.add_argument(
        "proposal_file",
        help="Path to a YAML technology proposal",
    )

    technology_subparsers.add_parser(
        "approve",
        help="Approve the technology proposal after human review",
    )

    args = parser.parse_args()

    if args.command == "init":
        try:
            project_root = initialize_project(
                project_name=args.project_name,
                target_dir=Path.cwd(),
            )

            print(f"Project created: {project_root}")
            print(f"Factory state: {project_root / '.factory' / 'state.yaml'}")

        except FileExistsError as error:
            parser.error(str(error))

    elif args.command == "status":
        show_status(Path.cwd())

    elif args.command == "next":
        state_path = Path.cwd() / ".factory" / "state.yaml"
        state = load_state(state_path)

        next_agent = get_next_agent(state)

        if next_agent:
            print(next_agent)
        else:
            print("none")

    elif args.command == "run":
        project_root = Path.cwd()
        config_path = project_root / ".factory" / "project.yaml"

        try:
            config = load_state(config_path)
            provider = create_provider(config)

            agent_name, output = run_next_agent(
                project_root=project_root,
                provider=provider,
            )

            print(
                render_agent_result(
                    agent_name,
                    output,
                )
            )

        except ValueError as error:
            parser.error(str(error))

    elif args.command == "resume":
        project_root = Path.cwd()
        state_path = project_root / ".factory" / "state.yaml"
        config_path = project_root / ".factory" / "project.yaml"

        state = load_state(state_path)
        config = load_state(config_path)

        try:
            state = resume_agent_with_input(
                project_root=project_root,
                state=state,
                project_config=config,
                agent_name=args.agent_name,
            )

            save_state(
                state_path,
                state,
            )

            print(
                f"Agent '{args.agent_name}' resumed and set to READY."
            )

        except (ValueError, KeyError) as error:
            parser.error(str(error))

    elif args.command == "retry":
        project_root = Path.cwd()
        state_path = project_root / ".factory" / "state.yaml"

        state = load_state(state_path)

        try:
            state = retry_agent(
                state,
                args.agent_name,
            )

            save_state(
                state_path,
                state,
            )

            print(
                f"Agent '{args.agent_name}' reset to READY for retry."
            )

        except (ValueError, KeyError) as error:
            parser.error(str(error))

    elif args.command == "set-status":
        state_path = Path.cwd() / ".factory" / "state.yaml"
        state = load_state(state_path)

        try:
            state = set_agent_status(
                state,
                args.agent_name,
                args.status,
                project_root=Path.cwd(),
            )

            save_state(state_path, state)

            print(
                f"{args.agent_name} status updated to {args.status}"
            )

        except (ValueError, KeyError) as error:
            parser.error(str(error))

    elif args.command == "approve":
        state_path = Path.cwd() / ".factory" / "state.yaml"
        state = load_state(state_path)

        try:
            state = apply_approval(
                state,
                args.approval_name,
                project_root=Path.cwd(),
            )

            save_state(state_path, state)

            print(
                f"Human approval recorded: {args.approval_name}"
            )

        except ValueError as error:
            parser.error(str(error))

    elif args.command == "design":
        if args.design_command == "rebuild":
            project_root = Path.cwd()
            state = load_state(
                project_root / ".factory" / "state.yaml"
            )

            state = rebuild_design_gate_from_state(
                state,
            )

            save_state(
                project_root / ".factory" / "state.yaml",
                state,
            )

            print(
                "Design Gate rebuilt from persisted UX/UI results."
            )
            return

    elif args.command == "technology":
        state_path = Path.cwd() / ".factory" / "state.yaml"
        project_config_path = Path.cwd() / ".factory" / "project.yaml"

        state = load_state(state_path)
        config = load_state(project_config_path)

        if args.technology_command == "status":
            technology = config.get("technology", {})
            gate = state.get("technology_gate", {})

            selection_mode = technology.get(
                "selection_mode",
                "unknown",
            )

            print("Technology:")
            print(f"  Selection mode:    {selection_mode}")
            print(
                f"  Gate status:       "
                f"{gate.get('status', 'UNKNOWN')}"
            )
            print(
                "  Human approval:    "
                + (
                    "approved"
                    if gate.get("human_approval", False)
                    else "pending"
                )
            )
            print(
                "  Gate approved:     "
                + (
                    "yes"
                    if is_technology_gate_approved(state)
                    else "no"
                )
            )

            proposal = gate.get("proposal", {})

            if proposal:
                print("  Proposal:           available")
            else:
                print("  Proposal:           none")

        elif args.technology_command == "submit":
            proposal_path = Path(args.proposal_file)

            if not proposal_path.is_absolute():
                proposal_path = Path.cwd() / proposal_path

            try:
                proposal = load_state(proposal_path)

                state = submit_technology_proposal(
                    state,
                    config,
                    proposal,
                )

                save_state(state_path, state)

                print("Technology proposal submitted for human review.")

            except (ValueError, FileNotFoundError) as error:
                parser.error(str(error))

        elif args.technology_command == "approve":
            try:
                state = approve_technology_gate(
                    state
                )

                config = apply_approved_technology_to_config(
                    config=config,
                    state=state,
                )

                save_state(
                    state_path,
                    state,
                )

                save_state(
                    project_config_path,
                    config,
                )

                print(
                    "Technology proposal approved and applied to project "
                    "configuration."
                )

            except ValueError as error:
                parser.error(str(error))


if __name__ == "__main__":
    main()
