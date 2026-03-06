"""SQLAlchemy ORM 模型 — 严格对齐 docs/schema.md。"""

from sqlalchemy import CheckConstraint, Index, Integer, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tag(Base):
    """schema.md §1 — 标签管理。"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    color: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'#6B7280'")
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_tags_name", "name"),)

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name={self.name!r})>"


class Relation(Base):
    """schema.md §2 — 关联关系（phone/email/social/other）。"""

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "type IN ('phone', 'email', 'social', 'other')",
            name="ck_relations_type",
        ),
        Index("idx_relations_type", "type"),
    )

    def __repr__(self) -> str:
        return f"<Relation(id={self.id}, type={self.type!r}, value={self.value!r})>"


class Bookmark(Base):
    """schema.md §3 — 书签主表。tag_ids/urls/accounts 为 JSON TEXT，应用层校验。"""

    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pinyin_initials: Mapped[str] = mapped_column(Text, nullable=False)
    tag_ids: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    urls: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    accounts: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_bookmarks_name", "name"),
        Index("idx_bookmarks_pinyin", "pinyin_initials"),
        Index("idx_bookmarks_last_used", last_used_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<Bookmark(id={self.id!r}, name={self.name!r})>"


class Authentication(Base):
    """schema.md §4 — 认证表。单用户，id 固定为 1（CHECK 约束）。"""

    __tablename__ = "authentication"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    master_password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_user_key: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    kdf_algorithm: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'argon2id'")
    )
    kdf_iterations: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    kdf_memory: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("65536")
    )
    kdf_parallelism: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_login: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_authentication_single_user"),)

    def __repr__(self) -> str:
        return f"<Authentication(id={self.id}, email={self.email!r})>"
