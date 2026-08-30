from typing import Any


def merge_implementation_results(
    previous_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge implementation history by task_id.

    New results replace older results for the same task.
    Existing completed tasks that were not rerun are preserved.
    """

    merged: dict[str, dict[str, Any]] = {}

    order: list[str] = []

    for result in previous_results:
        if not isinstance(result, dict):
            continue

        task_id = result.get("task_id")

        if not isinstance(task_id, str) or not task_id.strip():
            continue

        if task_id not in merged:
            order.append(task_id)

        merged[task_id] = result

    for result in new_results:
        if not isinstance(result, dict):
            continue

        task_id = result.get("task_id")

        if not isinstance(task_id, str) or not task_id.strip():
            continue

        if task_id not in merged:
            order.append(task_id)

        merged[task_id] = result

    return [
        merged[task_id]
        for task_id in order
    ]
