from ai_factory.workflow import is_transition_allowed


def test_ready_can_move_to_in_progress() -> None:
    assert is_transition_allowed(
        "READY",
        "IN_PROGRESS",
    )


def test_ready_cannot_move_directly_to_completed() -> None:
    assert not is_transition_allowed(
        "READY",
        "COMPLETED",
    )


def test_in_progress_can_move_to_review_required() -> None:
    assert is_transition_allowed(
        "IN_PROGRESS",
        "REVIEW_REQUIRED",
    )


def test_review_required_can_move_to_approved() -> None:
    assert is_transition_allowed(
        "REVIEW_REQUIRED",
        "APPROVED",
    )


def test_approved_is_terminal() -> None:
    assert not is_transition_allowed(
        "APPROVED",
        "IN_PROGRESS",
    )