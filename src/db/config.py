"""数据库配置管理 — 持久化已知数据库列表和当前选中数据库。

配置文件默认位于 ~/.keeper/databases.json，格式:
{
  "databases": [
    {"path": "/path/to/keeper.db", "name": "keeper.db"}
  ],
  "current": "/path/to/keeper.db"
}
"""

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".keeper"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "databases.json"

_EMPTY_CONFIG: dict[str, Any] = {"databases": [], "current": None}


class DatabaseConfig:
    """读写已知数据库列表及当前选中数据库的 JSON 配置。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_FILE

    # ------ 读写 ------

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {**_EMPTY_CONFIG, "databases": []}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {**_EMPTY_CONFIG, "databases": []}

    def save(self, config: dict[str, Any]) -> None:
        """写入配置文件，自动创建父目录。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------ 查询 ------

    def get_databases(self) -> list[dict[str, str]]:
        return self.load().get("databases", [])

    def get_current(self) -> str | None:
        """返回当前选中数据库的绝对路径，未设置时返回 None。"""
        return self.load().get("current")

    # ------ 修改 ------

    def set_current(self, path: str) -> None:
        """设置当前数据库，同时确保该路径在列表中。"""
        config = self.load()
        config["current"] = path
        self._ensure_in_list(config, path)
        self.save(config)

    def add_database(self, path: str) -> None:
        """将路径加入已知列表（去重）。"""
        config = self.load()
        self._ensure_in_list(config, path)
        self.save(config)

    def remove_database(self, path: str) -> None:
        """从已知列表中移除指定路径。"""
        config = self.load()
        config["databases"] = [
            db for db in config.get("databases", []) if db["path"] != path
        ]
        if config.get("current") == path:
            config["current"] = None
        self.save(config)

    # ------ 内部 ------

    @staticmethod
    def _ensure_in_list(config: dict[str, Any], path: str) -> None:
        """确保 path 存在于 databases 列表中。"""
        dbs = config.setdefault("databases", [])
        if not any(db["path"] == path for db in dbs):
            name = Path(path).name
            dbs.append({"path": path, "name": name})
