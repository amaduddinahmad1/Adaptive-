"""Add created_by_user_id to job_postings for recruiter data isolation

Revision ID: e4b7c2a9d6f1
Revises: d1f6a2b8c4e9
Create Date: 2026-09-17 16:00:00.000000

Jobs are owned by the recruiter who created them. Existing rows are
assigned to the lowest-id recruiter when one exists so legacy postings
remain visible to a deterministic valid owner. Rows stay nullable when
no recruiter account exists yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c2a9d6f1"
down_revision: Union[str, Sequence[str], None] = "d1f6a2b8c4e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_job_postings_created_by_user_id"),
        "job_postings",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_job_postings_created_by_user_id_users"),
        "job_postings",
        "users",
        ["created_by_user_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE job_postings
        SET created_by_user_id = (
            SELECT id FROM users
            WHERE role = 'recruiter'
            ORDER BY id ASC
            LIMIT 1
        )
        WHERE created_by_user_id IS NULL
          AND EXISTS (
              SELECT 1 FROM users WHERE role = 'recruiter'
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_job_postings_created_by_user_id_users"),
        "job_postings",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_job_postings_created_by_user_id"),
        table_name="job_postings",
    )
    op.drop_column("job_postings", "created_by_user_id")
