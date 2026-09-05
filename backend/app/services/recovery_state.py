from fastapi import HTTPException

from app.models.enums import RecoveryCaseStatus


TERMINAL_STATUSES = {
    RecoveryCaseStatus.RECOVERED,
    RecoveryCaseStatus.STOPPED,
    RecoveryCaseStatus.ESCALATED,
}


def assert_automatic_action_allowed(status: RecoveryCaseStatus) -> None:
    if status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Automatic recovery is not allowed after a case is {status.value}.",
        )
