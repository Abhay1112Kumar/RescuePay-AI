"""Internal payment state machine.

Every status change goes through :func:`assert_transition`, so an impossible
transition is a programming error that surfaces immediately instead of
silently corrupting a payment record.

States
------
PENDING          Record created; PayPal order not created yet.
CREATED          PayPal order exists; awaiting buyer approval.
APPROVED         Buyer approved at PayPal (observed via order lookup).
CAPTURING        Capture request in flight. Acts as a lock against duplicates.
CAPTURE_PENDING  PayPal accepted the capture but funds are not yet confirmed
                 (e.g. e-check). Resolved later by lookup or webhook.
COMPLETED        Funds captured. Terminal.
FAILED           Unrecoverable failure (provider error, mismatch). Terminal.
VOIDED           Order cancelled or expired at PayPal. Terminal.
"""

from enum import StrEnum


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    CREATION_UNCERTAIN = "CREATION_UNCERTAIN"
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    CAPTURING = "CAPTURING"
    CAPTURE_PENDING = "CAPTURE_PENDING"
    CAPTURE_UNCERTAIN = "CAPTURE_UNCERTAIN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VOIDED = "VOIDED"


TERMINAL_STATES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.COMPLETED, PaymentStatus.FAILED, PaymentStatus.VOIDED}
)

# States from which a capture may be started.
CAPTURABLE_STATES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.CREATED, PaymentStatus.APPROVED}
)

ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.CREATED, PaymentStatus.FAILED, PaymentStatus.CREATION_UNCERTAIN}
    ),
    PaymentStatus.CREATION_UNCERTAIN: frozenset(
        {PaymentStatus.CREATED, PaymentStatus.FAILED}
    ),
    PaymentStatus.CREATED: frozenset(
        {
            PaymentStatus.APPROVED,
            PaymentStatus.CAPTURING,
            PaymentStatus.CAPTURE_UNCERTAIN,
            PaymentStatus.CAPTURE_PENDING,
            PaymentStatus.COMPLETED,  # captured out-of-band, observed via lookup
            PaymentStatus.VOIDED,
            PaymentStatus.FAILED,
        }
    ),
    PaymentStatus.APPROVED: frozenset(
        {
            PaymentStatus.CAPTURING,
            PaymentStatus.CAPTURE_UNCERTAIN,
            PaymentStatus.CAPTURE_PENDING,
            PaymentStatus.COMPLETED,
            PaymentStatus.VOIDED,
            PaymentStatus.FAILED,
        }
    ),
    PaymentStatus.CAPTURING: frozenset(
        {
            PaymentStatus.COMPLETED,
            PaymentStatus.CAPTURE_PENDING,
            PaymentStatus.CAPTURE_UNCERTAIN,
            PaymentStatus.FAILED,
            PaymentStatus.VOIDED,  # order found voided during pre-capture verification
            # Capture did not happen (not approved, declined, uncertain outcome):
            # release the lock so a later attempt can proceed.
            PaymentStatus.APPROVED,
            PaymentStatus.CREATED,
        }
    ),
    PaymentStatus.CAPTURE_PENDING: frozenset(
        {PaymentStatus.COMPLETED, PaymentStatus.FAILED, PaymentStatus.CAPTURE_UNCERTAIN}
    ),
    PaymentStatus.CAPTURE_UNCERTAIN: frozenset(
        {PaymentStatus.COMPLETED, PaymentStatus.CAPTURE_PENDING, PaymentStatus.FAILED}
    ),
    PaymentStatus.COMPLETED: frozenset(),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.VOIDED: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    """Raised when code attempts a transition the state machine forbids."""

    def __init__(self, current: PaymentStatus, target: PaymentStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid payment transition {current} -> {target}")


def can_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def is_terminal(status: PaymentStatus) -> bool:
    return status in TERMINAL_STATES
