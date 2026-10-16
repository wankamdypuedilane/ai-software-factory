from pathlib import Path

import pytest

from ai_factory.test_runner import (
    run_test_command,
)


def test_run_test_command_executes_allowed_command(
    tmp_path: Path,
) -> None:
    result = run_test_command(
        project_root=tmp_path,
        command="python -m pytest --version",
    )

    assert result.returncode == 0
    assert result.passed is True
    assert result.command == "python -m pytest --version"


def test_run_test_command_captures_utf8_output(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test_utf8_output.py"
    test_file.write_text(
        "import sys\n\n"
        "def test_utf8_output():\n"
        "    sys.stdout.buffer.write('café\\n'.encode('utf-8'))\n",
        encoding="utf-8",
    )

    result = run_test_command(
        project_root=tmp_path,
        command="python -m pytest test_utf8_output.py -q -s",
    )

    assert result.passed is True
    assert "café" in result.stdout


def test_run_test_command_rejects_unsafe_command(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="Unsafe shell syntax",
    ):
        run_test_command(
            project_root=tmp_path,
            command="pytest && echo unsafe",
        )


def test_run_test_command_supplies_prisma_database_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(
        "ai_factory.test_runner.run_shell_command",
        fake_run,
    )

    run_test_command(
        project_root=tmp_path,
        command="npm run prisma:validate",
    )

    assert captured["env"] is not None
    assert (
        captured["env"]["DATABASE_URL"]
        == "postgresql://user:password@localhost:5432/factory_local"
    )


def test_run_test_command_supplies_database_url_to_node_tests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(
        "ai_factory.test_runner.run_shell_command",
        fake_run,
    )

    run_test_command(
        project_root=tmp_path,
        command=(
            "npm test -- "
            "src/modules/tasks/task-repository.test.ts"
        ),
    )

    assert captured["env"] is not None
    assert (
        captured["env"]["DATABASE_URL"]
        == "postgresql://user:password@localhost:5432/factory_local"
    )


def test_run_test_command_preserves_existing_database_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://real:test@db:5432/example",
    )

    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(
        "ai_factory.test_runner.run_shell_command",
        fake_run,
    )

    run_test_command(
        project_root=tmp_path,
        command="npm test",
    )

    assert (
        captured["env"]["DATABASE_URL"]
        == "postgresql://real:test@db:5432/example"
    )


def test_engine_source_declares_no_pilot_database_name() -> None:
    import ai_factory.test_runner as module

    source = Path(module.__file__).read_text(
        encoding="utf-8",
    )

    assert "taskflow" not in source.lower()


def test_default_database_url_is_generic_without_project_identity() -> None:
    from ai_factory.test_runner import (
        build_default_database_url,
    )

    url = build_default_database_url(())

    assert url.endswith("/factory_local")


def test_default_database_url_is_derived_from_project_identity() -> None:
    from ai_factory.test_runner import (
        build_default_database_url,
    )

    assert build_default_database_url(
        ("link", "vault")
    ).endswith("/link_vault")

    assert build_default_database_url(
        ("acme",)
    ).endswith("/acme")


def test_run_test_command_derives_the_database_name_from_the_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(
        "ai_factory.test_runner.run_shell_command",
        fake_run,
    )

    run_test_command(
        project_root=tmp_path,
        command="npm test",
        project_identity=("link", "vault"),
    )

    assert (
        captured["env"]["DATABASE_URL"]
        == "postgresql://user:password@localhost:5432/link_vault"
    )
