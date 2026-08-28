import argparse
from pathlib import Path

from ai_factory.approvals import approve
from ai_factory.orchestrator import get_next_agent
from ai_factory.project import initialize_project
from ai_factory.state import load_state, save_state
from ai_factory.transitions import set_agent_status


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

    elif args.command == "set-status":
        state_path = Path.cwd() / ".factory" / "state.yaml"
        state = load_state(state_path)

        try:
            state = set_agent_status(
                state,
                args.agent_name,
                args.status,
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
            state = approve(
                state,
                args.approval_name,
            )

            save_state(state_path, state)

            print(
                f"Human approval recorded: {args.approval_name}"
            )

        except ValueError as error:
            parser.error(str(error))


if __name__ == "__main__":
    main()
