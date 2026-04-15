# Keeper

Keeper 是一个**本地自部署的密码管理器后端 API**，专为浏览器扩展（Firefox/Chrome/Safari）提供安全的数据服务。

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  keeper-firefox │────▶│                 │◄────│ keeper-chrome   │
└─────────────────┘     │  Keeper API     │     └─────────────────┘
                        │  (Rust + Axum)  │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  SQLite (本地)  │
                        │  加密数据存储   │
                        └─────────────────┘
```

## 核心特性

- **🔒 安全优先**
  - 主密码使用 Argon2id 哈希（64MB 内存，3 次迭代）
  - 账户密码使用 AES-256-GCM 认证加密
  - 加密密钥仅存于内存，重启后消失
  - 会话令牌使用 256-bit 熵，支持滑动窗口刷新

- **🏠 本地自部署**
  - 所有数据存储在本地 SQLite 数据库
  - 不经过任何云服务，数据完全自主控制
  - 支持多数据库管理和切换

- **👤 单用户设计**
  - 每个数据库仅支持一个用户（`authentication.id = 1` 约束）
  - 简化认证流程，适合个人使用

- **🔍 中文搜索优化**
  - 自动计算拼音首字母和全拼
  - 支持拼音模糊搜索

- **📦 数据导入导出**
  - 支持 JSON 格式备份和恢复
  - 导出时密码解密为明文（需主密码验证）

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Rust | 2021 Edition |
| Web 框架 | Axum | 基于 Tokio 的异步 Web 框架 |
| 数据库 | SQLite | rusqlite 同步模式 (journal_mode = DELETE) |
| 密码哈希 | Argon2id | argon2 crate |
| 数据加密 | AES-256-GCM | aes-gcm crate |
| 密钥派生 | PBKDF2-HMAC-SHA256 | ring crate |
| 拼音 | pinyin | 支持中文搜索 |
| 序列化 | serde | JSON 处理 |

## 项目结构

```
keeper/
├── Cargo.toml              # 项目配置
├── Cargo.lock              # 依赖锁定
├── LICENSE                 # MIT 许可证
├── src/
│   ├── main.rs             # 应用入口
│   ├── lib.rs              # 库入口
│   ├── config.rs           # CLI 配置解析
│   ├── state.rs            # 应用状态（DB 连接 + 会话管理器）
│   ├── error.rs            # 错误类型定义
│   ├── crypto/             # 加密模块
│   │   ├── kdf.rs          # 密钥派生（Argon2id + PBKDF2）
│   │   └── encryption.rs   # AES-256-GCM 加密服务
│   ├── db/                 # 数据库层
│   │   ├── models.rs       # 数据模型定义
│   │   ├── connection.rs   # SQLite 连接管理
│   │   ├── migrate.rs      # 数据库迁移
│   │   └── config.rs       # 数据库配置管理
│   ├── handlers/           # API 处理器
│   │   ├── auth.rs         # 认证（初始化/解锁/锁定/状态）
│   │   ├── bookmarks.rs    # 书签 CRUD、搜索
│   │   ├── database.rs     # 数据库管理
│   │   ├── relations.rs    # 关联关系管理
│   │   ├── tags.rs         # 标签管理
│   │   ├── stats.rs        # 统计信息
│   │   ├── transfer.rs     # 导入/导出
│   │   └── schemas.rs      # 请求/响应 Schema
│   ├── middleware/         # 中间件
│   │   └── auth.rs         # 认证中间件（JWT Token 验证）
│   ├── session/            # 会话管理
│   │   └── manager.rs      # 内存会话管理器
│   └── utils/              # 工具函数
│       └── pinyin.rs       # 拼音计算
├── tests/                  # 集成测试
│   ├── auth_api_test.rs
│   ├── crypto_interop_test.rs
│   ├── relations_api_test.rs
│   ├── stats_api_test.rs
│   ├── tags_api_test.rs
│   └── transfer_api_test.rs
└── docs/                   # 文档
    └── rust-refactor-*.md  # 重构文档
```

## 快速开始

### 1. 构建

```bash
# 克隆仓库
git clone https://github.com/kimiellen/keeper.git
cd keeper

# 构建 release 版本
cargo build --release

# 或安装到系统
cargo install --path .
```

### 2. 运行

```bash
# 默认启动（监听 127.0.0.1:51000）
cargo run --release

# 指定地址和端口
cargo run --release -- -H 0.0.0.0 -p 8080

# 指定配置目录（Windows 用户常用）
cargo run --release -- -c "D:\Keeper\Config"

# 查看所有参数
keeper --help
```

### 启动服务

```bash
# 默认启动（监听 127.0.0.1:51000，配置保存在系统数据目录）
./keeper

# 指定配置目录（推荐 Windows 用户使用）
./keeper -c "C:\Users\Name\KeeperConfig"

# 查看帮助
./keeper --help
```

### 认证流程

1. **初始化**: `POST /api/auth/initialize` - 设置主密码和邮箱（仅首次）
2. **解锁**: `POST /api/auth/unlock` - 验证密码，获取访问 Token
3. **请求**: 在后续请求中通过 `Authorization: Bearer <token>` 头部携带 Token
4. **锁定**: `POST /api/auth/lock` - 清除会话，使 Token 失效

### Token 特性

- **有效期**: 默认 60 分钟，可通过 `/api/auth/session-timeout` 调整
- **滑动窗口**: 每次请求自动刷新过期时间
- **内存存储**: 重启服务后所有 Token 失效
- **单会话**: 同一时刻只有一个活跃会话，新解锁会踢掉旧会话

## 数据模型

### Tag（标签）
```rust
{
  id: i64,
  name: String,
  color: String,  // 默认 #3B82F6
  icon: String,
  created_at: DateTime<Utc>,
  updated_at: DateTime<Utc>,
}
```

### Relation（关联关系）
```rust
{
  id: i64,
  name: String,
  value: Option<String>,
  type: "phone" | "email" | "idcard" | "other",
  created_at: DateTime<Utc>,
  updated_at: DateTime<Utc>,
}
```

### Bookmark（书签/密码条目）
```rust
{
  id: String,  // UUID v4
  name: String,
  pinyin_initials: String,  // 拼音首字母（用于搜索）
  pinyin_full: String,      // 完整拼音（用于搜索）
  tag_ids: Vec<i64>,
  urls: Vec<UrlEntry>,
  notes: String,
  accounts: Vec<AccountEntry>,  // 密码加密存储
  created_at: DateTime<Utc>,
  updated_at: DateTime<Utc>,
  last_used_at: DateTime<Utc>,
}
```

### AccountEntry（账户条目）
```rust
{
  id: i64,
  username: String,
  password: String,  // AES-256-GCM 加密，格式: v1.AES_GCM.<nonce>.<ciphertext>.<tag>
  related_ids: Vec<i64>,  // 关联的 Relation ID
  created_at: DateTime<Utc>,
  last_used: DateTime<Utc>,
}
```

## API 端点

### 公开端点（无需认证）

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/auth/status` | 获取认证状态 |
| POST | `/api/auth/initialize` | 初始化主密码 |
| POST | `/api/auth/unlock` | 解锁（登录） |
| POST | `/api/auth/lock` | 锁定（登出） |
| GET | `/api/db/list` | 列出所有数据库 |
| POST | `/api/db/add` | 添加数据库 |
| POST | `/api/db/open` | 切换数据库 |
| POST | `/api/db/create` | 创建新数据库 |
| POST | `/api/db/remove` | 移除数据库 |

### 受保护端点（需 Bearer Token）

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/auth/info` | 获取用户信息 |
| POST | `/api/auth/session-timeout` | 设置会话超时 |
| GET | `/api/tags` | 列出标签 |
| POST | `/api/tags` | 创建标签 |
| GET | `/api/tags/:id` | 获取标签 |
| PUT | `/api/tags/:id` | 更新标签 |
| DELETE | `/api/tags/:id` | 删除标签 |
| GET | `/api/relations` | 列出关联 |
| POST | `/api/relations` | 创建关联 |
| GET | `/api/relations/:id` | 获取关联 |
| PUT | `/api/relations/:id` | 更新关联 |
| DELETE | `/api/relations/:id` | 删除关联 |
| GET | `/api/bookmarks` | 列出书签 |
| POST | `/api/bookmarks` | 创建书签 |
| GET | `/api/bookmarks/:id` | 获取书签 |
| PUT | `/api/bookmarks/:id` | 更新书签 |
| PATCH | `/api/bookmarks/:id` | 部分更新书签 |
| DELETE | `/api/bookmarks/:id` | 删除书签 |
| POST | `/api/bookmarks/:id/use` | 更新使用时间 |
| GET | `/api/stats` | 获取统计信息 |
| POST | `/api/export` | 导出数据 |
| POST | `/api/import` | 导入数据 |

## 数据库配置

数据库列表和当前选中数据库存储在配置目录的 `databases.json` 文件中：

- **Linux**: `~/.local/share/keeper/databases.json`
- **macOS**: `~/Library/Application Support/keeper/databases.json`
- **Windows**: `%APPDATA%\keeper\databases.json`

可通过 `--config-dir` / `-c` 参数自定义配置目录。

```json
{
  "databases": [
    {"path": "/home/user/keeper.db", "name": "keeper.db"},
    {"path": "/home/user/work.db", "name": "work.db"}
  ],
  "current": "/home/user/keeper.db"
}
```

## 加密详情

### 密码哈希（Argon2id）

```rust
Params {
    memory_cost: 65536,  // 64 MiB
    time_cost: 3,        // 3 次迭代
    parallelism: 1,      // 单线程
    output_length: 32,   // 32 字节输出
}
```

### 加密密钥派生（PBKDF2）

```rust
pbkdf2::derive(
    PBKDF2_HMAC_SHA256,
    100_000,                                    // 迭代次数
    b"keeper-encryption-key-v1",               // 固定盐
    master_password.as_bytes(),
    &mut key,                                   // 32 字节输出
);
```

### 数据加密格式

```
v1.AES_GCM.<nonce_base64>.<ciphertext_base64>.<tag_base64>
```

- **版本**: `v1`
- **算法**: `AES_GCM`
- **Nonce**: 12 字节（96-bit），随机生成
- **Tag**: 16 字节（128-bit）认证标签

## 测试

```bash
# 运行所有测试
cargo test

# 运行特定模块测试
cargo test crypto
cargo test session
cargo test handlers

# 运行集成测试
cargo test --test auth_api_test
cargo test --test bookmarks_api_test
```

## 浏览器扩展

Keeper 为以下浏览器扩展提供后端服务：

- [keeper-firefox](https://github.com/kimiellen/keeper-firefox) - Firefox 扩展
- [keeper-chrome](https://github.com/kimiellen/keeper-chrome) - Chrome 扩展

## 数据备份

由于使用标准 SQLite (journal_mode = DELETE)，推荐以下备份方式：

### 方法 1: 使用 SQLite 备份命令（推荐）
```bash
# 在线备份（不中断服务）
sqlite3 keeper.db ".backup to backup.db"

# 或导出为 SQL
sqlite3 keeper.db ".dump" > backup.sql
```

### 方法 2: 在前端插件中进行导出
导出为 JSON（包含明文密码，需主密码验证）

### 方法 3: 直接复制（确保服务未运行）
```bash
# 停止服务后复制
cp keeper.db keeper.db.backup.$(date +%Y%m%d)
```

## 安全注意事项

1. **本地绑定**: 默认绑定 `127.0.0.1`，如需外网访问请使用反向代理（如 Nginx + HTTPS）
2. **主密码**: 请使用强密码，遗失主密码将无法恢复数据
3. **备份**: 定期使用导出功能备份数据,导出的json是明文,不依赖前后端软件也能保存内容.(但需保障json文件的存储安全)

## 许可证

[MIT License](LICENSE)

Copyright (c) 2026 kimiellen
