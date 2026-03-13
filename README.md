# Keeper

本地部署的密码管理器后端 API。为 [keeper-firefox](https://github.com/kimiellen/keeper-firefox) 和 [keeper-chrome](https://github.com/kimiellen/keeper-chrome) 浏览器扩展提供数据服务。

**设计理念**：单用户、本地自部署、安全优先。所有数据存储在本机 SQLite 数据库中，不经过任何云服务或第三方服务器。

## 项目关系

```
keeper-firefox  ──┐
                  ├──▶  keeper（本仓库，后端 API）
keeper-chrome   ──┘
```

浏览器扩展通过 HTTPS REST API 与后端通信。后端 CORS 默认允许 `moz-extension://`（Firefox）和 `chrome-extension://`（Chrome）来源。

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| Web 框架 | FastAPI 0.115+ |
| ASGI 服务器 | uvicorn 0.32+ |
| ORM | SQLAlchemy 2.0（async） |
| 数据库 | SQLite + WAL 模式（aiosqlite） |
| 数据验证 | Pydantic 2.10+ |
| 密码哈希 | argon2-cffi（Argon2id 算法） |
| 数据加密 | cryptography（AES-256-GCM） |
| 认证方式 | 内存 Session Token + httpOnly Cookie |
| 包管理 | uv |

**认证机制**：解锁时生成随机 Token（`secrets.token_urlsafe`）存入内存，通过 `httponly + secure + samesite=strict` Cookie 传递，Session 有效期 1 小时。不使用 JWT。

**加密机制**：敏感字段使用 AES-256-GCM 加密，密钥由主密码经 Argon2id 派生，仅存于内存，重启或锁定后立即消失。

## 部署

### 前置条件

所有平台都需要安装 **Python 3.12+** 和 **uv** 包管理器。

浏览器扩展要求后端使用 **HTTPS**，需提前生成本地证书（推荐使用 [mkcert](https://github.com/FiloSottile/mkcert)）。

---

#### Linux

**安装 Python 3.12+**

```bash
# Ubuntu / Debian
sudo apt install python3.12

# Arch
sudo pacman -S python
```

**安装 uv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

**安装 mkcert 并生成证书**

```bash
# Ubuntu / Debian
sudo apt install mkcert
# Arch
sudo pacman -S mkcert

mkcert -install
mkdir -p certs
mkcert -key-file certs/localhost-key.pem -cert-file certs/localhost.pem localhost 127.0.0.1
```

**安装并启动**

```bash
git clone https://github.com/kimiellen/keeper.git
cd keeper
uv sync

# HTTPS 模式（推荐）
uv run uvicorn src.main:app --host 127.0.0.1 --port 8443 \
  --ssl-keyfile certs/localhost-key.pem \
  --ssl-certfile certs/localhost.pem
```

---

#### macOS

**安装 Python 3.12+**

```bash
brew install python@3.12
```

**安装 uv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

**安装 mkcert 并生成证书**

```bash
brew install mkcert
mkcert -install
mkdir -p certs
mkcert -key-file certs/localhost-key.pem -cert-file certs/localhost.pem localhost 127.0.0.1
```

**安装并启动**

```bash
git clone https://github.com/kimiellen/keeper.git
cd keeper
uv sync

# HTTPS 模式（推荐）
uv run uvicorn src.main:app --host 127.0.0.1 --port 8443 \
  --ssl-keyfile certs/localhost-key.pem \
  --ssl-certfile certs/localhost.pem
```

---

#### Windows

**安装 Python 3.12+**

从 [python.org](https://www.python.org/downloads/) 下载安装包，安装时勾选"Add Python to PATH"。

**安装 uv**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**安装 mkcert 并生成证书**

```powershell
# 使用 Scoop
scoop install mkcert
# 或使用 Chocolatey
choco install mkcert

mkcert -install
New-Item -ItemType Directory -Force -Path certs
mkcert -key-file certs\localhost-key.pem -cert-file certs\localhost.pem localhost 127.0.0.1
```

**安装并启动**

```powershell
git clone https://github.com/kimiellen/keeper.git
cd keeper
uv sync

# HTTPS 模式（推荐）
uv run uvicorn src.main:app --host 127.0.0.1 --port 8443 `
  --ssl-keyfile certs\localhost-key.pem `
  --ssl-certfile certs\localhost.pem
```

---

### 环境变量（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `KEEPER_CORS_ORIGINS` | 空 | 额外允许的 CORS origin，逗号分隔 |
| `KEEPER_CORS_ORIGIN_REGEX` | `^(moz-extension\|chrome-extension)://.*$` | CORS origin 正则匹配规则 |
| `KEEPER_SSL_KEYFILE` | `certs/localhost+2-key.pem` | SSL 私钥路径 |
| `KEEPER_SSL_CERTFILE` | `certs/localhost+2.pem` | SSL 证书路径 |

## 首次使用

后端启动后，需配合浏览器扩展完成初始化：

1. 安装 keeper-firefox 或 keeper-chrome 扩展
2. 在扩展中**新建数据库**（后端通过 `/api/db/create` 创建 SQLite 文件）
3. 设置**主密码**（通过 `/api/auth/initialize` 完成初始化）
4. 日常使用：打开扩展时输入主密码**解锁**，关闭时点击**锁定**

> 注意：后端启动时若无已配置的数据库，会等待扩展发起新建操作，不会自动创建默认数据库。

## API 文档

启动后在浏览器访问交互式文档：

- HTTP 模式：`http://localhost:8000/docs`
- HTTPS 模式：`https://localhost:8443/docs`

主要 API 分组：

| 分组 | 前缀 | 说明 |
|------|------|------|
| 认证 | `/api/auth` | 初始化、解锁、锁定、状态查询 |
| 数据库管理 | `/api/db` | 新建、切换、列表、删除数据库 |
| 书签 | `/api/bookmarks` | CRUD、搜索、批量操作 |
| 标签 | `/api/tags` | 标签管理 |
| 关联关系 | `/api/relations` | 书签与标签关联 |
| 导入导出 | `/api/transfer` | 数据备份与迁移 |
| 统计 | `/api/stats` | 数据统计信息 |

## 安全说明

- 主密码通过 Argon2id 哈希存储，永不明文保存
- 所有敏感字段（密码、账号等）使用 AES-256-GCM 加密
- 加密密钥由主密码派生，仅存于内存，锁定或重启后立即消失
- Session Token 1 小时自动过期
- httpOnly Cookie 防止 XSS 攻击窃取 Token
- 数据完全存储在本地，不依赖任何云服务

## 开发

```bash
# 运行测试
uv run pytest

# 带覆盖率报告
uv run pytest --cov=src

# HTTP 开发服务器（热重载）
uv run uvicorn src.main:app --reload
```

## 许可证

[MIT](LICENSE)
