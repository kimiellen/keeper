"""异步 SQLite 引擎和会话工厂。"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "keeper.db"

_SQLITE_CONNECT_ARGS = {
    "check_same_thread": False,
}


def get_database_url(db_path: str | Path | None = None) -> str:
    """构造 aiosqlite 连接 URL。`:memory:` 使用内存数据库，None 使用默认路径。"""
    if db_path is None:
        db_path = os.environ.get("KEEPER_DB_PATH", str(DEFAULT_DB_PATH))

    db_path = str(db_path)

    if db_path == ":memory:":
        return "sqlite+aiosqlite://"

    return f"sqlite+aiosqlite:///{db_path}"


def create_engine(db_path: str | Path | None = None, echo: bool = False):
    """创建 AsyncEngine。echo=True 输出 SQL 日志。"""
    url = get_database_url(db_path)
    return create_async_engine(
        url,
        echo=echo,
        connect_args=_SQLITE_CONNECT_ARGS,
    )


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """创建 async_sessionmaker，expire_on_commit=False。"""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
