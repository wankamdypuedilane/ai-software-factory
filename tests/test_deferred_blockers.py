from ai_factory.blocker_contract import (
    Blocker,
    BlockerKind,
    blocking_blockers,
    demote_deferred_blockers,
)
from ai_factory.implementation_prompt import build_implementation_prompt
from ai_factory.implementation_request import ImplementationTask


def _task(task_id: str, title: str = "Task") -> ImplementationTask:
    return ImplementationTask(agent_name="developer", id=task_id, title=title, purpose="p")


def test_blocker_deferring_to_a_later_unit_no_longer_blocks() -> None:
    blocker = Blocker(
        message="Les routes seront créées par RS-MVP-007 et RS-MVP-008.",
        requires_human_input=True,
    )

    demoted = demote_deferred_blockers([blocker], ["RS-MVP-007", "RS-MVP-009"])

    assert blocking_blockers(demoted) == []
    assert demoted[0].kind is BlockerKind.INFORMATION
    assert demoted[0].message == blocker.message


def test_unrelated_blocker_still_blocks() -> None:
    blocker = Blocker(message="Une clé SMTP réelle est requise.")

    assert blocking_blockers(demote_deferred_blockers([blocker], ["RS-MVP-007"])) == [blocker]
    assert blocking_blockers(demote_deferred_blockers([blocker], [])) == [blocker]


def test_prompt_lists_the_later_units() -> None:
    prompt = build_implementation_prompt(
        _task("RS-MVP-006"),
        {},
        later_tasks=[_task("RS-MVP-007", "Planning"), _task("RS-MVP-008", "Congés")],
    )

    assert "## Later Tasks Of This Plan" in prompt
    assert "- RS-MVP-007: Planning" in prompt
    assert "- RS-MVP-008: Congés" in prompt
