"""align tags and relations to api spec

Revision ID: a1b2c3d4e5f6
Revises: 539ef484bc80
Create Date: 2026-03-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "539ef484bc80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("icon", sa.Text(), server_default=sa.text("''"), nullable=False)
        )
        batch_op.add_column(sa.Column("updated_at", sa.Text(), nullable=True))

    op.execute("UPDATE tags SET updated_at = created_at WHERE updated_at IS NULL")

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.alter_column("updated_at", nullable=False)

    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name", sa.Text(), nullable=True, unique=True))
        batch_op.add_column(sa.Column("updated_at", sa.Text(), nullable=True))

    op.execute("UPDATE relations SET name = value WHERE name IS NULL")
    op.execute("UPDATE relations SET updated_at = created_at WHERE updated_at IS NULL")

    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.alter_column("name", nullable=False)
        batch_op.alter_column("updated_at", nullable=False)
        batch_op.drop_column("value")
        batch_op.drop_column("label")
        batch_op.drop_constraint("ck_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_relations_type",
            "type IN ('phone', 'email', 'idcard', 'other')",
        )


def downgrade() -> None:
    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("value", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("label", sa.Text(), server_default=sa.text("''"), nullable=False)
        )

    op.execute("UPDATE relations SET value = name WHERE value IS NULL")

    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.alter_column("value", nullable=False)
        batch_op.drop_column("name")
        batch_op.drop_column("updated_at")
        batch_op.drop_constraint("ck_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_relations_type",
            "type IN ('phone', 'email', 'social', 'other')",
        )

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.drop_column("icon")
        batch_op.drop_column("updated_at")
