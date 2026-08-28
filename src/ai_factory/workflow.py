ALLOWED_TRANSITIONS = {
    "NOT_STARTED": {"READY"},
    "READY": {"IN_PROGRESS"},
    "IN_PROGRESS": {
        "REVIEW_REQUIRED",
        "COMPLETED",
        "BLOCKED",
        "FAILED",
    },
    "REVIEW_REQUIRED": {
        "APPROVED",
        "FAILED",
        "BLOCKED",
    },
    "FAILED": {
        "READY",
        "IN_PROGRESS",
    },
    "BLOCKED": {
        "READY",
        "IN_PROGRESS",
    },
    "APPROVED": set(),
    "COMPLETED": set(),
}


def is_transition_allowed(
    current_status: str,
    new_status: str,
) -> bool:
    """Return whether a status transition is allowed."""

    allowed = ALLOWED_TRANSITIONS.get(current_status)

    if allowed is None:
        return False

    return new_status in allowed