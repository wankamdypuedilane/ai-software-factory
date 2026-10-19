import json
import os
import stat
import sys
from pathlib import Path

import pytest

from ai_factory.claude_code_provider import (
    ClaudeCodeProvider,
    collect_changes,
    extract_json,
    restore_snapshot,
    take_snapshot,
)
from ai_factory.provider_errors import ProviderErrorKind, ProviderExecutionError


pytestmark = pytest.mark.skipif(os.name == "nt", reason="fake executable uses a shebang")


def _fake_claude(tmp_path: Path, body: str) -> str:
    """A stand-in for the `claude` CLI: reads the prompt on stdin."""

    script = tmp_path / "fake-claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, os, pathlib\n"
        "args = sys.argv[1:]\n"
        "prompt = sys.stdin.read()\n"
        "pathlib.Path(os.environ.get('FAKE_LOG', '/dev/null')).write_text(json.dumps({'args': args, 'prompt': prompt}))\n"
        + body,
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "existing.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (root / ".factory").mkdir()
    (root / ".factory" / "state.yaml").write_text("agents: {}\n", encoding="utf-8")
    return root


def test_snapshot_collects_changes_and_restores_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = take_snapshot(root)

    (root / "src" / "existing.ts").write_text("export const a = 2;\n", encoding="utf-8")
    (root / "src" / "new.ts").write_text("export const b = 1;\n", encoding="utf-8")
    (root / "node_modules" / "pkg" / "index.js").write_text("changed", encoding="utf-8")
    (root / ".factory" / "state.yaml").write_text("tampered\n", encoding="utf-8")

    assert collect_changes(root, before) == {
        "src/existing.ts": "export const a = 2;\n",
        "src/new.ts": "export const b = 1;\n",
    }

    restore_snapshot(root, before)

    assert (root / "src" / "existing.ts").read_text(encoding="utf-8") == "export const a = 1;\n"
    assert not (root / "src" / "new.ts").exists()


@pytest.mark.parametrize(
    "text",
    ['{"ok": true}', 'Voici :\n```json\n{"ok": true}\n```', 'Done. {"ok": true} Bye.'],
)
def test_json_is_found_in_any_answer_shape(text: str) -> None:
    assert json.loads(extract_json(text)) == {"ok": True}


def test_implementation_returns_changed_files_and_leaves_the_project_untouched(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    executable = _fake_claude(
        tmp_path,
        "pathlib.Path('src/booking.ts').write_text('export const booking = true;\\n')\n"
        "pathlib.Path('tests').mkdir(exist_ok=True)\n"
        "pathlib.Path('tests/booking.test.mjs').write_text('test')\n"
        "final = {'task_id': 'RS-1', 'summary': 'Booking done', 'setup_commands': [], "
        "'tests': ['npm test -- tests/booking.test.mjs'], 'blockers': []}\n"
        "print(json.dumps({'type': 'result', 'is_error': False, 'result': json.dumps(final)}))\n",
    )
    provider = ClaudeCodeProvider(executable=executable)

    result = provider.implement_in_workspace("Task ID: RS-1\nDo it.", root)

    assert result.task_id == "RS-1"
    assert {change.path for change in result.files} == {"src/booking.ts", "tests/booking.test.mjs"}
    assert result.tests == ["npm test -- tests/booking.test.mjs"]
    assert not (root / "src" / "booking.ts").exists()

    call = json.loads(log.read_text(encoding="utf-8"))
    assert "--permission-mode" in call["args"] and "acceptEdits" in call["args"]
    assert "Run the task's targeted test commands yourself" in call["prompt"]


def test_project_is_restored_even_when_claude_code_fails(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executable = _fake_claude(
        tmp_path,
        "pathlib.Path('src/half.ts').write_text('broken')\n"
        "print(json.dumps({'type': 'result', 'is_error': True, 'result': 'Claude AI usage limit reached'}))\n"
        "sys.exit(1)\n",
    )
    provider = ClaudeCodeProvider(executable=executable)

    with pytest.raises(ProviderExecutionError) as error:
        provider.implement_in_workspace("Task ID: RS-1", root)

    assert error.value.kind is ProviderErrorKind.RATE_LIMITED
    assert not (root / "src" / "half.ts").exists()


def test_other_calls_are_read_only_and_parsed_like_openai(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    answer = {"cause": "c", "instruction": "i", "needs_human": False, "question": ""}
    executable = _fake_claude(
        tmp_path,
        f"print(json.dumps({{'type': 'result', 'is_error': False, 'result': 'Voici ```json\\n' + json.dumps({answer!r}) + '\\n```'}}))\n",
    )
    provider = ClaudeCodeProvider(executable=executable, models={"writing": "sonnet", "code": "opus"})

    assert provider.diagnose("why?") == answer

    call = json.loads(log.read_text(encoding="utf-8"))
    assert call["args"][call["args"].index("--permission-mode") + 1] == "dontAsk"
    assert "Bash,Edit,Write,NotebookEdit" in call["args"]
    assert call["args"][call["args"].index("--model") + 1] == "opus"  # diagnosis is code work
    assert "JSON Schema" in call["prompt"]


def test_not_signed_in_is_explained(tmp_path: Path) -> None:
    executable = _fake_claude(
        tmp_path,
        "print(json.dumps({'type': 'result', 'is_error': True, 'result': 'Not logged in · Please run /login'}))\n",
    )

    with pytest.raises(ProviderExecutionError, match="not signed in"):
        ClaudeCodeProvider(executable=executable).generate("doc")


def test_factory_builds_the_claude_code_provider(tmp_path: Path) -> None:
    from ai_factory.provider_factory import create_provider

    provider = create_provider(
        {"ai": {"provider": "claude-code", "settings": {"claude_executable": _fake_claude(tmp_path, "")}}}
    )

    assert isinstance(provider, ClaudeCodeProvider)


def test_a_weekly_limit_is_recognized_and_explained_in_french(tmp_path: Path) -> None:
    from ai_factory.web.service import friendly_error

    executable = _fake_claude(
        tmp_path,
        "print(json.dumps({'type': 'result', 'is_error': True, 'result': \"You've hit your weekly limit · resets 4pm (Europe/Paris)\"}))\n",
    )

    with pytest.raises(ProviderExecutionError) as error:
        ClaudeCodeProvider(executable=executable).generate("doc")

    assert error.value.kind is ProviderErrorKind.RATE_LIMITED
    assert friendly_error(str(error.value)).startswith("Ton abonnement Claude a atteint sa limite")
    assert "resets 4pm" in friendly_error(str(error.value))
