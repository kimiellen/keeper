"""数据库初始化：python -m src.init_db"""

import asyncio
import sys

from sqlalchemy import text

from src.db.engine import create_engine
from src.db.models import Base


async def init_database(db_path: str | None = None, echo: bool = False) -> None:
    """创建所有表，启用 WAL 模式和外键约束。"""
    engine = create_engine(db_path=db_path, echo=echo)

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()

    table_names = list(Base.metadata.tables.keys())
    print(f"Database initialized successfully. Tables created: {table_names}")


def main() -> None:

    echo = "--echo" in sys.argv
    asyncio.run(init_database(echo=echo))


if __name__ == "__main__":
    main()
