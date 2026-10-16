from pathlib import Path

from ai_factory.test_references import (
    build_missing_reference_correction,
    find_missing_test_references,
)


UI_TEST = """
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { importTypeScript } from "./helpers/import-typescript.mjs";

test("layout", async () => {
  const layout = await readFile("src/app/layout.tsx", "utf8");
  const css = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
  assert.match(layout, /lang="fr"/);
});
"""


def _project(tmp_path: Path) -> Path:
    (tmp_path / "tests" / "helpers").mkdir(parents=True)
    (tmp_path / "tests" / "helpers" / "import-typescript.mjs").write_text("export {}", encoding="utf-8")
    return tmp_path


def test_reports_files_a_test_reads_but_nobody_writes(tmp_path: Path) -> None:
    missing = find_missing_test_references(
        _project(tmp_path),
        {"tests/ui-foundation.test.mjs": UI_TEST},
    )

    assert missing == [
        ("tests/ui-foundation.test.mjs", "src/app/layout.tsx"),
        ("tests/ui-foundation.test.mjs", "src/app/globals.css"),
    ]


def test_files_written_in_the_response_or_existing_are_fine(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "globals.css").write_text("", encoding="utf-8")

    missing = find_missing_test_references(
        root,
        {
            "tests/ui-foundation.test.mjs": UI_TEST,
            "src/app/layout.tsx": "export default function Layout() {}",
        },
    )

    assert missing == []


def test_non_test_files_and_packages_are_ignored(tmp_path: Path) -> None:
    missing = find_missing_test_references(
        _project(tmp_path),
        {
            "src/app/page.tsx": 'import x from "../lib/missing.ts";',
            "tests/a.test.mjs": 'import pg from "pg"; import x from "@scope/pkg/index.js";',
        },
    )

    assert missing == []


def test_correction_names_each_missing_file() -> None:
    lines = build_missing_reference_correction(
        "RS-MVP-009",
        [("tests/ui-foundation.test.mjs", "src/app/layout.tsx")],
    )

    assert any("src/app/layout.tsx" in line for line in lines)
    assert any("RS-MVP-009" in line for line in lines)


def test_tests_only_response_is_detected() -> None:
    from ai_factory.test_references import writes_only_tests

    assert writes_only_tests(["tests/a.test.mjs", "tests/helpers/db.mjs"])
    assert not writes_only_tests(["tests/a.test.mjs", "src/server/route.ts"])
    assert not writes_only_tests([])


def test_helpers_are_shown_before_other_workspace_files() -> None:
    from ai_factory.implementation_prompt import build_implementation_prompt
    from ai_factory.implementation_request import ImplementationTask

    workspace = {f"src/big{index}.ts": "x" * 6000 for index in range(10)}
    workspace["tests/helpers/isolated-postgres.mjs"] = "export async function prepareTestDatabase() { return { env, dispose } }"

    prompt = build_implementation_prompt(
        ImplementationTask(agent_name="developer", id="T", title="t", purpose="p"),
        {},
        workspace_files=workspace,
    )

    assert "### tests/helpers/isolated-postgres.mjs\nexport async function prepareTestDatabase" in prompt
