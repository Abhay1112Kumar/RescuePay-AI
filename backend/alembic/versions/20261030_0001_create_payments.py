"""Create payments and payment_events tables

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=127), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("paypal_order_id", sa.String(length=64), nullable=True),
        sa.Column("paypal_capture_id", sa.String(length=64), nullable=True),
        sa.Column("create_request_id", sa.String(length=36), nullable=False),
        sa.Column("capture_request_id", sa.String(length=36), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paypal_order_id"),
        sa.UniqueConstraint("paypal_capture_id"),
        sa.UniqueConstraint("create_request_id"),
        sa.UniqueConstraint("capture_request_id"),
    )
    op.create_index("ix_payments_reference_id", "payments", ["reference_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("paypal_debug_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_reference_id", table_name="payments")
    op.drop_table("payments")
