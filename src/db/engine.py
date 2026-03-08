"""异步 SQLite 引擎和会话工厂。"""

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "keeper.db"

_SQLITE_CONNECT_ARGS = {
    "check_same_thread": False,
}


def _set_sqlite_pragmas(dbapi_conn, connection_record) -> None:  # type: ignore[no-untyped-def]
    """每次新建 SQLite 连接时设置性能和安全 PRAGMA。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-8000")  # 8 MB
    cursor.close()


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
    engine = create_async_engine(
        url,
        echo=echo,
        connect_args=_SQLITE_CONNECT_ARGS,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """创建 async_sessionmaker，expire_on_commit=False。"""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class DatabaseManager:
    """管理 SQLite 引擎生命周期，支持运行时热切换数据库。"""

    def __init__(self) -> None:
        self.engine = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.current_path: str | None = None

    async def initialize(self, db_path: str | Path | None = None) -> None:
        """为指定路径创建引擎和 session_factory，并确保表结构存在。"""
        resolved = str(db_path) if db_path else str(DEFAULT_DB_PATH)
        self.engine = create_engine(resolved)
        self.session_factory = create_session_factory(self.engine)
        self.current_path = resolved

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def switch(self, db_path: str | Path) -> None:
        """热切换到另一个数据库：关闭旧引擎，初始化新引擎。"""
        if self.engine is not None:
            await self.engine.dispose()
        await self.initialize(db_path)

    async def dispose(self) -> None:
        """关闭引擎，释放连接池。"""
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            self.current_path = None
