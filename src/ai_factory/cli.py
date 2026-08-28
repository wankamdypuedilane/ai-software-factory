import argparse
from pathlib import Path

from ai_factory.orchestrator import get_next_agent
from ai_factory.project import initialize_project
from ai_factory.state import load_state


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


if __name__ == "__main__":
    main()
