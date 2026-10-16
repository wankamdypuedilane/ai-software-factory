from pathlib import Path

from ai_factory.devops_prompt import build_devops_prompt
from ai_factory.security_prompt import build_security_prompt
from ai_factory.sre_prompt import build_sre_prompt
from ai_factory.validation_context import (
    add_validation_evidence,
    load_implemented_sources,
    summarize_executed_tests,
)


def test_load_implemented_sources_reads_project_files_only(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "todo").mkdir(parents=True)
    (project / "todo" / "service.py").write_text(
        "def add(): pass\n",
        encoding="utf-8",
    )
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    sources = load_implemented_sources(
        project,
        {
            "implemented_files": [
                "todo/service.py",
                "../secret.txt",
                "missing.py",
            ],
        },
    )

    assert sources == {"todo/service.py": "def add(): pass\n"}


def test_summarize_executed_tests_keeps_outcome_and_tail() -> None:
    summary = summarize_executed_tests(
        {
            "test_results": [
                {
                    "command": "python -m pytest",
                    "returncode": 0,
                    "stdout": "a" * 5000 + "46 passed",
                    "stderr": "",
                },
            ],
        }
    )

    assert summary[0]["passed"] is True
    assert summary[0]["stdout_tail"].endswith("46 passed")
    assert len(summary[0]["stdout_tail"]) == 2000


def test_add_validation_evidence_does_not_mutate_the_context(
    tmp_path: Path,
) -> None:
    context = {"project": {}}

    enriched = add_validation_evidence(
        context,
        project_root=tmp_path,
        developer_result={},
    )

    assert "implemented_sources" not in context
    assert enriched["implemented_sources"] == {}
    assert enriched["executed_tests"] == []
    assert enriched["validation_rules"]


def test_every_validator_prompt_states_the_execution_rules() -> None:
    context = {
        "implemented_sources": {"todo/storage.py": "import json"},
    }

    for prompt in (
        build_security_prompt(context),
        build_devops_prompt(context),
        build_sre_prompt(context),
    ):
        assert "## Execution and Scope" in prompt
        assert "Never report that you cannot execute tests" in prompt
        assert "local command-line tool" in prompt
        assert "import json" in prompt


def test_build_validation_outcome_uses_executed_evidence() -> None:
    from ai_factory.qa_result import QAResult
    from ai_factory.qa_runtime import QAExecution
    from ai_factory.test_runner import CommandExecutionResult
    from ai_factory.validation_context import build_validation_outcome

    execution = QAExecution(
        result=QAResult(
            summary="No defects.",
            passed=True,
            test_commands=["python -m pytest"],
        ),
        prompt="",
        test_results=[
            CommandExecutionResult(
                command="python -m pytest",
                returncode=0,
                stdout="50 passed",
                stderr="",
            ),
        ],
    )

    outcome = build_validation_outcome("qa", execution)

    assert outcome["passed"] is True
    assert outcome["items"] == []
    assert outcome["executed_tests"][0]["stdout_tail"] == "50 passed"
