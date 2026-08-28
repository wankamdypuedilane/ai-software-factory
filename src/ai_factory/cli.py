import argparse
from pathlib import Path

from ai_factory.project import initialize_project


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


if __name__ == "__main__":
    main()

    