"""Add nullable ingestion metadata without changing historical job values."""

import sqlalchemy as sa
from alembic import op


revision = "0002_ingestion_metadata"
down_revision = "0001_stage_1f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingestion_jobs", sa.Column("content_fingerprint", sa.String(64), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("updated_records", sa.Integer(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("unchanged_records", sa.Integer(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("duration_ms", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("failure_phase", sa.String(32), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("failure_code", sa.String(64), nullable=True))


def downgrade():
    for name in ("failure_code", "failure_phase", "duration_ms", "completed_at",
                 "started_at", "unchanged_records", "updated_records", "content_fingerprint"):
        op.drop_column("ingestion_jobs", name)
