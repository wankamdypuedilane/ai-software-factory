import sys
from pathlib import Path

from ai_factory.project_environment import (
    ENVIRONMENT_FILE,
    active_project_environment,
    load_project_environment,
    project_environment,
)
from ai_factory.test_runner import run_test_command


def _write(root: Path, text: str) -> None:
    path = root / ENVIRONMENT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_missing_file_means_no_variables(tmp_path: Path) -> None:
    assert load_project_environment(tmp_path) == {}


def test_file_is_parsed_leniently(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "# base de test\n"
        "TEST_DATABASE_URL=postgresql://u:p@localhost:5432/app_test\n"
        'export DATABASE_URL="postgresql://u:p@localhost:5432/app"\n'
        "not a variable\n"
        "1BAD=x\n",
    )

    assert load_project_environment(tmp_path) == {
        "TEST_DATABASE_URL": "postgresql://u:p@localhost:5432/app_test",
        "DATABASE_URL": "postgresql://u:p@localhost:5432/app",
    }


def test_variables_are_active_only_inside_the_run(tmp_path: Path) -> None:
    _write(tmp_path, "TEST_DATABASE_URL=x\n")

    with project_environment(tmp_path):
        assert active_project_environment() == {"TEST_DATABASE_URL": "x"}

    assert active_project_environment() == {}


def test_test_commands_receive_the_project_variables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "from-shell")
    monkeypatch.setattr(
        "ai_factory.test_runner.validate_test_command",
        lambda command: None,
    )
    _write(tmp_path, "TEST_DATABASE_URL=from-project\n")
    command = (
        f'"{sys.executable}" -c '
        '"import os; print(os.environ[\'TEST_DATABASE_URL\'])"'
    )

    with project_environment(tmp_path):
        result = run_test_command(tmp_path, command)

    assert result.passed, result.stderr
    assert result.stdout.strip() == "from-project"
