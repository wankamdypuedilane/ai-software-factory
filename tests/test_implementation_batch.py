from pathlib import Path

from ai_factory.agent_result import (
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.implementation_batch import (
    run_implementation_batch,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)


class FakeImplementationProvider:
    def __init__(
        self,
        results: list[ImplementationResult],
    ) -> None:
        self.results = list(results)
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompts.append(prompt)
        return self.results.pop(0)


def test_run_implementation_batch_executes_tasks_sequentially(
    tmp_path: Path,
) -> None:
    agent_result = AgentResult(
        status="COMPLETED",
        summary="Implementation planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="US-001",
                title="Authentication",
                purpose="Implement authentication.",
            ),
            AgentImplementationRequest(
                id="US-002",
                title="Ride creation",
                purpose="Implement ride creation.",
            ),
        ],
    )

    provider = FakeImplementationProvider(
        [
            ImplementationResult(
                task_id="US-001",
                summary="Authentication implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth.py",
                        content="# auth",
                    )
                ],
            ),
            ImplementationResult(
                task_id="US-002",
                summary="Ride creation implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/rides.py",
                        content="# rides",
                    )
                ],
            ),
        ]
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=agent_result,
        context={},
        provider=provider,
    )

    assert len(batch.results) == 2
    assert len(batch.written_files) == 2
    assert batch.blocked is False

    assert batch.results[0].task_id == "US-001"
    assert batch.results[1].task_id == "US-002"

    assert len(provider.prompts) == 2
    assert "Task ID: US-001" in provider.prompts[0]
    assert "Task ID: US-002" in provider.prompts[1]


def test_run_implementation_batch_stops_after_blocker(
    tmp_path: Path,
) -> None:
    agent_result = AgentResult(
        status="COMPLETED",
        summary="Implementation planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="US-001",
                title="Authentication",
                purpose="Implement authentication.",
            ),
            AgentImplementationRequest(
                id="US-002",
                title="Ride creation",
                purpose="Implement ride creation.",
            ),
            AgentImplementationRequest(
                id="US-003",
                title="Ride completion",
                purpose="Implement ride completion.",
            ),
        ],
    )

    provider = FakeImplementationProvider(
        [
            ImplementationResult(
                task_id="US-001",
                summary="Authentication implemented.",
            ),
            ImplementationResult(
                task_id="US-002",
                summary="Blocked.",
                blockers=[
                    "Ride state requirement is ambiguous.",
                ],
            ),
            ImplementationResult(
                task_id="US-003",
                summary="Should not execute.",
            ),
        ]
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=agent_result,
        context={},
        provider=provider,
    )

    assert batch.blocked is True
    assert len(batch.results) == 2
    assert len(provider.prompts) == 2

    assert batch.results[-1].task_id == "US-002"
    assert batch.results[-1].blockers == [
        "Ride state requirement is ambiguous."
    ]


def test_run_implementation_batch_handles_no_requests(
    tmp_path: Path,
) -> None:
    agent_result = AgentResult(
        status="COMPLETED",
        summary="Nothing to implement.",
    )

    provider = FakeImplementationProvider(
        []
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=agent_result,
        context={},
        provider=provider,
    )

    assert batch.results == []
    assert batch.written_files == []
    assert batch.blocked is False
    assert provider.prompts == []


def test_run_implementation_batch_stops_when_tests_fail(
    tmp_path: Path,
) -> None:
    agent_result = AgentResult(
        status="COMPLETED",
        summary="Implementation planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="US-001",
                title="Authentication",
                purpose="Implement authentication.",
            ),
            AgentImplementationRequest(
                id="US-002",
                title="Ride creation",
                purpose="Implement ride creation.",
            ),
        ],
    )

    class FailingTestProvider:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            self.prompts.append(prompt)

            if len(self.prompts) == 1:
                return ImplementationResult(
                    task_id="US-001",
                    summary="Authentication implemented.",
                    files=[
                        ImplementationFileChange(
                            path="tests/test_auth.py",
                            content=(
                                "def test_auth():\n"
                                "    assert False\n"
                            ),
                        )
                    ],
                    tests=[
                        "python -m pytest tests/test_auth.py -q",
                    ],
                )

            return ImplementationResult(
                task_id="US-002",
                summary="Should not execute.",
            )

    provider = FailingTestProvider()

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=agent_result,
        context={},
        provider=provider,
    )

    assert batch.test_failed is True
    assert batch.failed_task_id == "US-001"
    assert batch.blocked is False

    assert len(batch.results) == 1
    assert len(provider.prompts) == 1


def test_run_implementation_batch_skips_completed_tasks(
    tmp_path: Path,
) -> None:
    agent_result = AgentResult(
        status="COMPLETED",
        summary="Implementation planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="US-001",
                title="Authentication",
                purpose="Implement authentication.",
            ),
            AgentImplementationRequest(
                id="US-002",
                title="Ride creation",
                purpose="Implement ride creation.",
            ),
            AgentImplementationRequest(
                id="US-003",
                title="Ride completion",
                purpose="Implement ride completion.",
            ),
        ],
    )

    provider = FakeImplementationProvider(
        [
            ImplementationResult(
                task_id="US-002",
                summary="Ride creation implemented.",
            ),
            ImplementationResult(
                task_id="US-003",
                summary="Ride completion implemented.",
            ),
        ]
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=agent_result,
        context={},
        provider=provider,
        completed_task_ids={
            "US-001",
        },
    )

    assert len(batch.results) == 2

    assert [
        result.task_id
        for result in batch.results
    ] == [
        "US-002",
        "US-003",
    ]

    assert len(provider.prompts) == 2

    assert "Task ID: US-001" not in provider.prompts[0]
    assert "Task ID: US-002" in provider.prompts[0]
    assert "Task ID: US-003" in provider.prompts[1]

    assert batch.blocked is False
