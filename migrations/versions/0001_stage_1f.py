"""Stage 1F schema for an empty PostgreSQL database."""

from alembic import op
import sqlalchemy as sa


revision = "0001_stage_1f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "movies",
        sa.Column("movie_id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("genres", sa.String()),
        sa.Column("release_year", sa.Integer()),
    )
    op.create_index("ix_movies_movie_id", "movies", ["movie_id"])
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_table(
        "ratings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.movie_id"), primary_key=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.Integer()),
    )
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.movie_id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PLANNED"),
        sa.Column("added_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "movie_id", name="unique_user_movie"),
    )
    op.create_index("ix_watchlist_id", "watchlist", ["id"])
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_records", sa.Integer()),
        sa.Column("imported_records", sa.Integer()),
        sa.Column("rejected_records", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_ingestion_jobs_id", "ingestion_jobs", ["id"])


def downgrade():
    # PostgreSQL removes table-owned indexes and sequences with their table.
    for table in ("ingestion_jobs", "watchlist", "ratings", "users", "movies"):
        op.drop_table(table)
