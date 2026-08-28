import argparse


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

    parser.parse_args()


if __name__ == "__main__":
    main()

    