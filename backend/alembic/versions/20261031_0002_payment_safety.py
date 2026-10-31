"""Persist creation keys and optimistic payment versions; reverify legacy success.

Revision ID: 0002
Revises: 0001
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("creation_key", sa.String(36), nullable=True))
        batch.add_column(sa.Column("approval_url", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
        batch.create_unique_constraint("uq_payments_creation_key", ["creation_key"])
    # Old COMPLETED rows were accepted by weaker verification. They must pass
    # the stricter provider evidence checks before being reported as paid again.
    bind = op.get_bind()
    now = datetime.now(UTC).isoformat()
    rows = (
        bind.execute(sa.text("SELECT id FROM payments WHERE status = 'COMPLETED'"))
        .scalars()
        .all()
    )
    for payment_id in rows:
        bind.execute(
            sa.text(
                "INSERT INTO payment_events (payment_id, event_type, from_status, to_status, detail, created_at) "
                "VALUES (:payment_id, 'payment.verification_upgrade', 'COMPLETED', 'CAPTURE_UNCERTAIN', "
                "'Reverify capture with stricter evidence checks', :now)"
            ),
            {"payment_id": payment_id, "now": now},
        )
    bind.execute(
        sa.text(
            "UPDATE payments SET status = 'CAPTURE_UNCERTAIN', updated_at = :now WHERE status = 'COMPLETED'"
        ),
        {"now": now},
    )


def downgrade() -> None:
    # Do not downgrade an unresolved payment into a state the old code can
    # capture again. Resolve it first; do not silently discard safety state.
    unresolved = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM payments WHERE status IN ('CAPTURE_UNCERTAIN', 'CREATION_UNCERTAIN')"
            )
        )
        .scalar_one()
    )
    if unresolved:
        raise RuntimeError(
            "Resolve uncertain payments before downgrading payment safety."
        )
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("uq_payments_creation_key", type_="unique")
        batch.drop_column("version")
        batch.drop_column("approval_url")
        batch.drop_column("creation_key")
