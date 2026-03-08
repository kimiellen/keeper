"""add pinyin_full to bookmarks

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from xpinyin import Pinyin


revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _compute_initials(name: str, pinyin: Pinyin) -> str:
    result: list[str] = []
    i = 0
    while i < len(name):
        ch = name[i]
        if "\u4e00" <= ch <= "\u9fff":
            result.append(pinyin.get_initials(ch, "").lower())
            i += 1
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < len(name) and name[j].isascii() and name[j].isalpha():
                j += 1
            segment = name[i:j]
            uppers = [c for c in segment if c.isupper()]
            if uppers:
                result.append("".join(uppers).lower())
            else:
                result.append(segment[0].lower())
            i = j
        else:
            i += 1
    return "".join(result)[:50]


def upgrade() -> None:
    with op.batch_alter_table("bookmarks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "pinyin_full",
                sa.Text(),
                server_default=sa.text("''"),
                nullable=False,
            )
        )
        batch_op.create_index("idx_bookmarks_pinyin_full", ["pinyin_full"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM bookmarks")).fetchall()
    if rows:
        _pinyin = Pinyin()
        for row in rows:
            pinyin_full = _pinyin.get_pinyin(row[1], "").lower()
            initials = _compute_initials(row[1], _pinyin)
            conn.execute(
                sa.text(
                    "UPDATE bookmarks SET pinyin_full = :pf, pinyin_initials = :pi"
                    " WHERE id = :id"
                ),
                {"pf": pinyin_full, "pi": initials, "id": row[0]},
            )


def downgrade() -> None:
    with op.batch_alter_table("bookmarks", schema=None) as batch_op:
        batch_op.drop_index("idx_bookmarks_pinyin_full")
        batch_op.drop_column("pinyin_full")
