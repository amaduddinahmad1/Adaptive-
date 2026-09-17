"""Add job interview_question_count and application hiring_decision

Revision ID: c9d4e8a1b7f2
Revises: f13c7ba3c4f3
Create Date: 2026-09-17 13:05:00.000000

Existing job_postings rows receive interview_question_count=7 (the runtime
default that matches the sample Day 2 question list). Existing applications
receive hiring_decision='pending'. Neither column replaces eligibility or
InterviewResult data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d4e8a1b7f2"
down_revision: Union[str, Sequence[str], None] = "f13c7ba3c4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column(
            "interview_question_count",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    )
    op.add_column(
        "applications",
        sa.Column(
            "hiring_decision",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index(
        op.f("ix_applications_hiring_decision"),
        "applications",
        ["hiring_decision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_applications_hiring_decision"), table_name="applications")
    op.drop_column("applications", "hiring_decision")
    op.drop_column("job_postings", "interview_question_count")
