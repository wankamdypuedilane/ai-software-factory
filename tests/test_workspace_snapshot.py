from pathlib import Path

from ai_factory.workspace_snapshot import (
    build_workspace_snapshot,
    extract_workspace_paths_from_test_results,
    get_default_workspace_context_paths,
)


def test_build_workspace_snapshot_reads_existing_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "lib" / "http.ts"
    source.parent.mkdir(parents=True)

    source.write_text(
        "export function parseJson() {}",
        encoding="utf-8",
    )

    snapshot = build_workspace_snapshot(
        project_root=tmp_path,
        file_paths=[
            "src/lib/http.ts",
        ],
    )

    assert snapshot == {
        "src/lib/http.ts": "export function parseJson() {}",
    }


def test_build_workspace_snapshot_ignores_missing_files(
    tmp_path: Path,
) -> None:
    snapshot = build_workspace_snapshot(
        project_root=tmp_path,
        file_paths=[
            "src/missing.ts",
        ],
    )

    assert snapshot == {}


def test_build_workspace_snapshot_rejects_paths_outside_project(
    tmp_path: Path,
) -> None:
    snapshot = build_workspace_snapshot(
        project_root=tmp_path,
        file_paths=[
            "../outside.txt",
        ],
    )

    assert snapshot == {}


def test_extract_workspace_paths_from_test_results() -> None:
    test_results = [
        {
            "command": "npm run typecheck",
            "stdout": (
                "src/lib/http.test.ts(35,47): error TS2322\n"
                "src/lib/errors.ts(31,27): error TS2339"
            ),
            "stderr": "",
        },
        {
            "command": "npm test",
            "stdout": "",
            "stderr": (
                "FAIL src/lib/http.test.ts > shared HTTP handling\n"
                "src/lib/http.ts:45:31"
            ),
        },
    ]

    paths = extract_workspace_paths_from_test_results(
        test_results
    )

    assert paths == [
        "src/lib/http.test.ts",
        "src/lib/errors.ts",
        "src/lib/http.ts",
    ]


def test_get_default_workspace_context_paths_includes_existing_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"zod":"3.24.1"}}',
        encoding="utf-8",
    )

    assert get_default_workspace_context_paths(
        tmp_path
    ) == [
        "package.json",
    ]


def test_get_default_workspace_context_paths_ignores_missing_manifests(
    tmp_path: Path,
) -> None:
    assert get_default_workspace_context_paths(
        tmp_path
    ) == []


def test_retry_diagnostic_paths_are_bounded_and_prioritized() -> None:
    from ai_factory.workspace_snapshot import prioritize_diagnostic_paths

    paths = [
        "src/app/api/v1/auth/_helpers.ts",
        "src/app/api/v1/auth/register/route.ts",
        "src/lib/http.test.ts",
        "src/lib/prisma.test.ts",
        "src/lib/prisma.ts",
        "src/modules/identity/auth.test.ts",
        "src/modules/identity/domain/credentials.ts",
        "src/modules/identity/rate-limit.test.ts",
        "src/modules/identity/session-service.test.ts",
        "src/modules/tasks/domain.test.ts",
        "src/modules/tasks/task-repository.test.ts",
        "src/modules/tasks/task-repository.ts",
        "src/modules/tasks/repository.ts",
        "prisma/schema.contract.test.ts",
    ]

    result = prioritize_diagnostic_paths(
        paths,
        task_id="TASKFLOW-DEV-TASK-REPOSITORY",
        limit=8,
    )

    assert len(result) <= 8

    assert "src/modules/tasks/task-repository.ts" in result
    assert "src/modules/tasks/task-repository.test.ts" in result
    assert "src/modules/tasks/repository.ts" in result


def test_diagnostic_path_relevance_uses_task_identity() -> None:
    from ai_factory.workspace_snapshot import (
        is_diagnostic_path_relevant_to_task,
    )

    assert is_diagnostic_path_relevant_to_task(
        "src/modules/tasks/task-repository.test.ts",
        task_id="TASKFLOW-DEV-TASK-REPOSITORY",
    )

    assert is_diagnostic_path_relevant_to_task(
        "src/app/api/v1/tasks/_helpers.ts",
        task_id="TASKFLOW-DEV-TASK-API-LIST-CREATE",
    )

    assert not is_diagnostic_path_relevant_to_task(
        "src/modules/tasks/task-repository.test.ts",
        task_id="TASKFLOW-DEV-TASK-API-LIST-CREATE",
    )


def test_expand_workspace_paths_with_local_imports_resolves_alias_import(
    tmp_path: Path,
) -> None:
    from ai_factory.workspace_snapshot import (
        expand_workspace_paths_with_local_imports,
    )

    route = tmp_path / "src" / "app" / "api" / "v1" / "tasks" / "route.ts"
    domain = tmp_path / "src" / "modules" / "tasks" / "domain.ts"

    route.parent.mkdir(parents=True)
    domain.parent.mkdir(parents=True)

    route.write_text(
        'import { taskSchema } from "@/modules/tasks/domain";\n',
        encoding="utf-8",
    )
    domain.write_text(
        "export const taskSchema = {};\n",
        encoding="utf-8",
    )

    paths = expand_workspace_paths_with_local_imports(
        project_root=tmp_path,
        file_paths=["src/app/api/v1/tasks/route.ts"],
    )

    assert "src/app/api/v1/tasks/route.ts" in paths
    assert "src/modules/tasks/domain.ts" in paths


def test_expand_workspace_paths_with_local_imports_resolves_relative_import(
    tmp_path: Path,
) -> None:
    from ai_factory.workspace_snapshot import (
        expand_workspace_paths_with_local_imports,
    )

    route = tmp_path / "src" / "app" / "route.ts"
    helper = tmp_path / "src" / "app" / "_helpers.ts"

    route.parent.mkdir(parents=True)

    route.write_text(
        'import { helper } from "./_helpers";\n',
        encoding="utf-8",
    )
    helper.write_text(
        "export const helper = true;\n",
        encoding="utf-8",
    )

    paths = expand_workspace_paths_with_local_imports(
        project_root=tmp_path,
        file_paths=["src/app/route.ts"],
    )

    assert "src/app/route.ts" in paths
    assert "src/app/_helpers.ts" in paths


def test_expand_workspace_paths_with_local_imports_ignores_packages(
    tmp_path: Path,
) -> None:
    from ai_factory.workspace_snapshot import (
        expand_workspace_paths_with_local_imports,
    )

    route = tmp_path / "src" / "app" / "route.ts"
    route.parent.mkdir(parents=True)

    route.write_text(
        'import { z } from "zod";\n',
        encoding="utf-8",
    )

    paths = expand_workspace_paths_with_local_imports(
        project_root=tmp_path,
        file_paths=["src/app/route.ts"],
    )

    assert paths == ["src/app/route.ts"]


def test_engine_source_contains_no_pilot_project_name() -> None:
    import ai_factory.workspace_snapshot as module

    source = Path(module.__file__).read_text(
        encoding="utf-8",
    )

    assert "taskflow" not in source.lower()


def test_normalize_project_identity_handles_compound_names() -> None:
    from ai_factory.workspace_snapshot import (
        normalize_project_identity,
    )

    assert normalize_project_identity(
        "ShopLite"
    ) == ("shop", "lite")
    assert normalize_project_identity(
        "Shop Lite"
    ) == ("shop", "lite")
    assert normalize_project_identity(
        "shop-lite"
    ) == ("shop", "lite")
    assert normalize_project_identity(
        "SHOP_LITE"
    ) == ("shop", "lite")
    assert normalize_project_identity(
        "TaskFlow"
    ) == ("task", "flow")
    assert normalize_project_identity(
        None
    ) == ()
    assert normalize_project_identity(
        "   "
    ) == ()


def test_resolve_project_identity_reads_the_workflow_state() -> None:
    from ai_factory.workspace_snapshot import (
        resolve_project_identity,
    )

    assert resolve_project_identity(
        {
            "state": {
                "project": {
                    "id": "shop-lite",
                    "name": "ShopLite",
                }
            }
        }
    ) == ("shop", "lite")

    assert resolve_project_identity(
        {
            "project": {
                "project": {
                    "name": "Invoice Hub",
                }
            }
        }
    ) == ("invoice", "hub")

    assert resolve_project_identity({}) == ()


def test_project_name_in_a_path_is_not_relevant_to_every_task() -> None:
    from ai_factory.workspace_snapshot import (
        is_diagnostic_path_relevant_to_task,
    )

    assert not is_diagnostic_path_relevant_to_task(
        "src/shoplite/ui/button.tsx",
        task_id="SHOPLITE-DEV-CART-REPOSITORY",
        project_identity=("shop", "lite"),
    )

    assert not is_diagnostic_path_relevant_to_task(
        "shoplite.config.ts",
        task_id="SHOPLITE-DEV-AUTH-SESSION",
        project_identity=("shop", "lite"),
    )


def test_task_related_path_stays_relevant_in_another_project() -> None:
    from ai_factory.workspace_snapshot import (
        is_diagnostic_path_relevant_to_task,
    )

    assert is_diagnostic_path_relevant_to_task(
        "src/modules/cart/cart-repository.ts",
        task_id="SHOPLITE-DEV-CART-REPOSITORY",
        project_identity=("shop", "lite"),
    )


def test_project_name_sharing_a_word_with_a_feature() -> None:
    from ai_factory.workspace_snapshot import (
        is_diagnostic_path_relevant_to_task,
    )

    # "shop" is both half of the project name and a real feature.
    assert is_diagnostic_path_relevant_to_task(
        "src/modules/shop/settings.ts",
        task_id="SHOPLITE-DEV-SHOP-SETTINGS",
        project_identity=("shop", "lite"),
    )

    # The project directory itself must stay irrelevant.
    assert not is_diagnostic_path_relevant_to_task(
        "src/shoplite/ui/button.tsx",
        task_id="SHOPLITE-DEV-SHOP-SETTINGS",
        project_identity=("shop", "lite"),
    )


def test_taskflow_relevance_is_unchanged() -> None:
    from ai_factory.workspace_snapshot import (
        is_diagnostic_path_relevant_to_task,
    )

    identity = ("task", "flow")

    assert is_diagnostic_path_relevant_to_task(
        "src/modules/tasks/task-repository.test.ts",
        task_id="TASKFLOW-DEV-TASK-REPOSITORY",
        project_identity=identity,
    )

    assert is_diagnostic_path_relevant_to_task(
        "src/app/api/v1/tasks/_helpers.ts",
        task_id="TASKFLOW-DEV-TASK-API-LIST-CREATE",
        project_identity=identity,
    )

    assert not is_diagnostic_path_relevant_to_task(
        "src/modules/tasks/task-repository.test.ts",
        task_id="TASKFLOW-DEV-TASK-API-LIST-CREATE",
        project_identity=identity,
    )


def test_prioritize_diagnostic_paths_accepts_project_identity() -> None:
    from ai_factory.workspace_snapshot import (
        prioritize_diagnostic_paths,
    )

    paths = [
        "src/shoplite/ui/button.tsx",
        "src/modules/cart/cart-repository.ts",
        "src/modules/cart/cart-repository.test.ts",
    ]

    result = prioritize_diagnostic_paths(
        paths,
        task_id="SHOPLITE-DEV-CART-REPOSITORY",
        project_identity=("shop", "lite"),
        limit=2,
    )

    assert result == [
        "src/modules/cart/cart-repository.test.ts",
        "src/modules/cart/cart-repository.ts",
    ]
