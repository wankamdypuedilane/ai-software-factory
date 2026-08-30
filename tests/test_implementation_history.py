from ai_factory.implementation_history import (
    merge_implementation_results,
)


def test_merge_implementation_results_preserves_completed_history() -> None:
    previous_results = [
        {
            "task_id": "US-001",
            "summary": "Authentication implemented.",
            "tests": [],
            "blockers": [],
            "files": [
                "src/auth.py",
            ],
        },
        {
            "task_id": "US-002",
            "summary": "Blocked.",
            "tests": [],
            "blockers": [
                "Requirement is ambiguous.",
            ],
            "files": [],
        },
    ]

    new_results = [
        {
            "task_id": "US-002",
            "summary": "Ride creation implemented.",
            "tests": [],
            "blockers": [],
            "files": [
                "src/rides.py",
            ],
        },
        {
            "task_id": "US-003",
            "summary": "Ride completion implemented.",
            "tests": [],
            "blockers": [],
            "files": [
                "src/completion.py",
            ],
        },
    ]

    merged = merge_implementation_results(
        previous_results=previous_results,
        new_results=new_results,
    )

    assert [
        result["task_id"]
        for result in merged
    ] == [
        "US-001",
        "US-002",
        "US-003",
    ]

    assert merged[0]["summary"] == (
        "Authentication implemented."
    )

    assert merged[1]["summary"] == (
        "Ride creation implemented."
    )

    assert merged[1]["blockers"] == []

    assert merged[2]["summary"] == (
        "Ride completion implemented."
    )


def test_merge_implementation_results_adds_new_tasks() -> None:
    merged = merge_implementation_results(
        previous_results=[],
        new_results=[
            {
                "task_id": "US-001",
                "summary": "Implemented.",
            }
        ],
    )

    assert merged == [
        {
            "task_id": "US-001",
            "summary": "Implemented.",
        }
    ]


def test_merge_implementation_results_ignores_invalid_entries() -> None:
    merged = merge_implementation_results(
        previous_results=[
            {},
            {
                "task_id": "",
            },
        ],
        new_results=[
            {
                "task_id": "US-001",
                "summary": "Implemented.",
            }
        ],
    )

    assert merged == [
        {
            "task_id": "US-001",
            "summary": "Implemented.",
        }
    ]
