"""Tests for the payment state machine."""

import pytest

from app.services.payment_state import (
    ALLOWED_TRANSITIONS,
    CAPTURABLE_STATES,
    TERMINAL_STATES,
    InvalidTransitionError,
    PaymentStatus,
    assert_transition,
    can_transition,
    is_terminal,
)


def test_every_status_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(PaymentStatus)


@pytest.mark.parametrize("status", sorted(TERMINAL_STATES))
def test_terminal_states_have_no_exits(status: PaymentStatus) -> None:
    assert ALLOWED_TRANSITIONS[status] == frozenset()
    assert is_terminal(status)


@pytest.mark.parametrize("status", sorted(set(PaymentStatus) - TERMINAL_STATES))
def test_non_terminal_states_have_exits(status: PaymentStatus) -> None:
    assert ALLOWED_TRANSITIONS[status]
    assert not is_terminal(status)


def test_capturable_states_can_enter_capturing() -> None:
    for status in CAPTURABLE_STATES:
        assert can_transition(status, PaymentStatus.CAPTURING)


def test_happy_path_sequence() -> None:
    path = [
        PaymentStatus.PENDING,
        PaymentStatus.CREATED,
        PaymentStatus.APPROVED,
        PaymentStatus.CAPTURING,
        PaymentStatus.COMPLETED,
    ]
    for current, nxt in zip(path, path[1:], strict=False):
        assert_transition(current, nxt)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (PaymentStatus.PENDING, PaymentStatus.COMPLETED),  # must go through PayPal
        (PaymentStatus.PENDING, PaymentStatus.APPROVED),
        (PaymentStatus.COMPLETED, PaymentStatus.FAILED),
        (PaymentStatus.COMPLETED, PaymentStatus.CAPTURING),
        (PaymentStatus.VOIDED, PaymentStatus.CREATED),
        (PaymentStatus.FAILED, PaymentStatus.APPROVED),
        (PaymentStatus.CAPTURE_PENDING, PaymentStatus.CAPTURING),
    ],
)
def test_forbidden_transitions_raise(
    current: PaymentStatus, target: PaymentStatus
) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError) as exc_info:
        assert_transition(current, target)
    assert exc_info.value.current is current
    assert exc_info.value.target is target


def test_capturing_can_release_lock_backwards() -> None:
    assert can_transition(PaymentStatus.CAPTURING, PaymentStatus.APPROVED)
    assert can_transition(PaymentStatus.CAPTURING, PaymentStatus.CREATED)
