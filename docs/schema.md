# Keeper 数据库设计文档

## 项目概述

Keeper 是一个本地优先的密码管理器，采用客户端加密和零知识架构。本文档定义了后端 API 的数据库模式。

**相关项目**：
- **keeper**（本项目）：后端 API - FastAPI + SQLite + Argon2id 加密
- **keeper-firefox**：浏览器扩展 - WXT + Vue 3 + TypeScript（位于 `../keeper-firefox`）

---

## 数据库表结构

### 1. Tag 表（标签管理）

标签是用户自定义的分类维度，用于组织书签。插件中有专门的标签管理页面。

#### 表结构
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6B7280',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_tags_name ON tags(name);
```

#### 字段说明
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY | 自增主键 |
| `name` | TEXT | NOT NULL, UNIQUE | 标签名称（唯一） |
| `color` | TEXT | DEFAULT '#6B7280' | 十六进制颜色值（用于 UI 显示） |
| `created_at` | TEXT | NOT NULL | ISO 8601 格式时间戳 |

#### JSON 示例
```json
{
  "id": 1,
  "name": "工作",
  "color": "#3B82F6",
  "createdAt": "2026-01-10T08:00:00Z"
}
```

---

### 2. Relation 表（关联关系管理）

关联关系记录用户的联系方式（手机/邮箱/社交账号），用于追踪网站账号的注册途径。插件中有专门的关联管理页面。

#### 表结构
```sql
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('phone', 'email', 'social', 'other')),
    value TEXT NOT NULL,
    label TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_relations_type ON relations(type);
```

#### 字段说明
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY | 自增主键 |
| `type` | TEXT | NOT NULL, CHECK | 类型枚举：`phone` / `email` / `social` / `other` |
| `value` | TEXT | NOT NULL | 实际值（手机号/邮箱/社交账号） |
| `label` | TEXT | DEFAULT '' | 显示标签（如"主手机号"、"工作邮箱"） |
| `created_at` | TEXT | NOT NULL | ISO 8601 格式时间戳 |

#### JSON 示例
```json
{
  "id": 1,
  "type": "phone",
  "value": "+86 138****1234",
  "label": "主手机号",
  "createdAt": "2026-01-10T08:00:00Z"
}
```

---

### 3. Bookmark 表（书签主表）

书签表存储网站信息和账号凭证。支持纯书签（无账号）和带账号的书签两种场景。

#### 表结构
```sql
CREATE TABLE bookmarks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    pinyin_initials TEXT NOT NULL,
    tag_ids TEXT NOT NULL DEFAULT '[]',
    urls TEXT NOT NULL,
    notes TEXT DEFAULT '',
    accounts TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL
);

CREATE INDEX idx_bookmarks_name ON bookmarks(name);
CREATE INDEX idx_bookmarks_pinyin ON bookmarks(pinyin_initials);
CREATE INDEX idx_bookmarks_last_used ON bookmarks(last_used_at DESC);
```

#### 字段说明
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | UUID 字符串 |
| `name` | TEXT | NOT NULL | 书签名称 |
| `pinyin_initials` | TEXT | NOT NULL | 拼音首字母（自动生成，用于中文搜索，如"GitHub" → "gh"） |
| `tag_ids` | TEXT | NOT NULL | JSON 数组，存储 Tag 表的 id（如 `[1, 3, 5]`） |
| `urls` | TEXT | NOT NULL | JSON 数组，存储 URL 对象（至少 1 个） |
| `notes` | TEXT | DEFAULT '' | 备注信息（长文本） |
| `accounts` | TEXT | NOT NULL | JSON 数组，存储账号对象（可为空 `[]`） |
| `created_at` | TEXT | NOT NULL | 创建时间（ISO 8601） |
| `updated_at` | TEXT | NOT NULL | 最后更新时间（ISO 8601） |
| `last_used_at` | TEXT | NOT NULL | 最后使用时间（用于"最近使用"排序） |

#### JSON 字段详细说明

**urls 数组结构**：
```json
[
  {
    "url": "https://github.com",
    "lastUsed": "2026-03-06T10:30:00Z"
  },
  {
    "url": "https://github.com/login",
    "lastUsed": "2026-03-05T15:20:00Z"
  }
]
```

**accounts 数组结构**：
```json
[
  {
    "id": 1,
    "username": "kimiellen",
    "password": "encrypted_base64_string_here",
    "relatedIds": [1, 3],
    "createdAt": "2026-01-15T08:00:00Z",
    "lastUsed": "2026-03-06T10:30:00Z"
  }
]
```

**accounts 字段说明**：
- `id`：账号编号（同一 bookmark 内唯一，手动递增）
- `username`：用户名/邮箱/手机号
- `password`：加密后的密码（AES-256-GCM + Base64）
- `relatedIds`：关联 ID 数组（引用 Relation 表的 id，可为空 `[]`）
- `createdAt`：账号创建时间
- `lastUsed`：账号最后使用时间

#### 完整 JSON 示例

**带账号的书签**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "GitHub",
  "pinyinInitials": "gh",
  "tagIds": [1, 3],
  "urls": [
    {
      "url": "https://github.com",
      "lastUsed": "2026-03-06T10:30:00Z"
    },
    {
      "url": "https://github.com/login",
      "lastUsed": "2026-03-05T15:20:00Z"
    }
  ],
  "notes": "个人开发账号，双因素认证已启用",
  "accounts": [
    {
      "id": 1,
      "username": "kimiellen",
      "password": "AES256GCM:nonce:ciphertext:tag",
      "relatedIds": [1, 3],
      "createdAt": "2026-01-15T08:00:00Z",
      "lastUsed": "2026-03-06T10:30:00Z"
    }
  ],
  "createdAt": "2026-01-15T08:00:00Z",
  "updatedAt": "2026-03-06T10:30:00Z",
  "lastUsedAt": "2026-03-06T10:30:00Z"
}
```

**纯书签（无账号）**：
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "MDN Web Docs",
  "pinyinInitials": "mdn",
  "tagIds": [3, 5],
  "urls": [
    {
      "url": "https://developer.mozilla.org",
      "lastUsed": "2026-03-05T09:15:00Z"
    }
  ],
  "notes": "Web开发参考文档",
  "accounts": [],
  "createdAt": "2026-02-01T10:00:00Z",
  "updatedAt": "2026-03-05T09:15:00Z",
  "lastUsedAt": "2026-03-05T09:15:00Z"
}
```

---

### 4. Authentication 表（用户认证）

存储主密码的派生参数和加密的用户密钥。单用户场景，只有一条记录（id=1）。

#### 表结构
```sql
CREATE TABLE authentication (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    email TEXT NOT NULL UNIQUE,
    master_password_hash TEXT NOT NULL,
    encrypted_user_key TEXT NOT NULL,
    recovery_code_hash TEXT NOT NULL,
    kdf_algorithm TEXT NOT NULL DEFAULT 'argon2id',
    kdf_iterations INTEGER NOT NULL DEFAULT 3,
    kdf_memory INTEGER NOT NULL DEFAULT 65536,
    kdf_parallelism INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT NOT NULL
);
```

#### 字段说明
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, CHECK | 固定为 1（单用户限制） |
| `email` | TEXT | NOT NULL, UNIQUE | 用户邮箱（用作 Argon2id 的 salt） |
| `master_password_hash` | TEXT | NOT NULL | Argon2id 哈希（用于服务器端认证） |
| `encrypted_user_key` | TEXT | NOT NULL | 加密的 User Key（用 Master Key 加密） |
| `recovery_code_hash` | TEXT | NOT NULL | 恢复码的 Argon2id 哈希（用于忘记主密码时重置） |
| `kdf_algorithm` | TEXT | NOT NULL | 密钥派生算法（固定 `argon2id`） |
| `kdf_iterations` | INTEGER | NOT NULL | Argon2id 时间成本（默认 2） |
| `kdf_memory` | INTEGER | NOT NULL | Argon2id 内存成本（KB，默认 16384 = 16MB，本地场景优化） |
| `kdf_parallelism` | INTEGER | NOT NULL | Argon2id 并行度（默认 4） |
| `created_at` | TEXT | NOT NULL | 账户创建时间（ISO 8601） |
| `last_login` | TEXT | NOT NULL | 最后登录时间（ISO 8601） |

#### JSON 示例
```json
{
  "id": 1,
  "email": "beginner.zealots@gmail.com",
  "masterPasswordHash": "$argon2id$v=19$m=16384,t=2,p=4$c2FsdA$hash...",
  "encryptedUserKey": "AES256GCM:nonce:ciphertext:tag",
  "recoveryCodeHash": "$argon2id$v=19$m=16384,t=2,p=4$c2FsdA$recovery_hash...",
  "kdfAlgorithm": "argon2id",
  "kdfIterations": 2,
  "kdfMemory": 16384,
  "kdfParallelism": 4,
  "createdAt": "2026-01-10T08:00:00Z",
  "lastLogin": "2026-03-06T10:00:00Z"
}
```

---

## 数据关系

### 外键约束与级联删除

由于 SQLite 对 JSON 字段内的外键支持有限，需要在应用层处理级联删除逻辑：

#### 删除 Tag 时
```python
# 1. 从所有 bookmarks 的 tag_ids 数组中移除该 tag_id
# 2. 删除 tag 记录
def delete_tag(tag_id: int):
    # 读取所有包含该 tag_id 的书签
    cursor.execute("""
        SELECT id, tag_ids FROM bookmarks
        WHERE json_each.value = ?
        AND json_each.key IN (SELECT key FROM json_each(tag_ids))
    """, (tag_id,))
    
    # 更新每个书签，移除 tag_id
    for bookmark_id, tag_ids_json in cursor.fetchall():
        tag_ids = json.loads(tag_ids_json)
        tag_ids.remove(tag_id)
        cursor.execute(
            "UPDATE bookmarks SET tag_ids = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tag_ids), datetime.now().isoformat(), bookmark_id)
        )
    
    # 删除 tag
    cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
```

#### 删除 Relation 时
```python
# 1. 从所有 bookmarks 的 accounts[].relatedIds 中移除该 relation_id
# 2. 删除 relation 记录
def delete_relation(relation_id: int):
    cursor.execute("SELECT id, accounts FROM bookmarks")
    
    for bookmark_id, accounts_json in cursor.fetchall():
        accounts = json.loads(accounts_json)
        modified = False
        
        for account in accounts:
            if relation_id in account.get('relatedIds', []):
                account['relatedIds'].remove(relation_id)
                modified = True
        
        if modified:
            cursor.execute(
                "UPDATE bookmarks SET accounts = ?, updated_at = ? WHERE id = ?",
                (json.dumps(accounts), datetime.now().isoformat(), bookmark_id)
            )
    
    cursor.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
```

### 数据约束

1. **tagIds 数组**：可为空 `[]`，必须是有效 JSON 数组
2. **urls 数组**：至少包含 1 个 URL 对象
3. **accounts 数组**：可为空 `[]`（纯书签场景）
4. **relatedIds 数组**：可为空 `[]`
5. **级联删除规则**：
   - 删除 Tag → 清理 bookmarks.tag_ids
   - 删除 Relation → 清理 accounts[].relatedIds
   - 删除 Bookmark → 不影响 Tag/Relation 表（可被多个 bookmark 共享）
6. **时间格式**：统一使用 ISO 8601（`2026-03-06T10:30:00Z`）

---

## 加密方案

### 密钥派生架构（参考 Bitwarden）

Keeper 采用零知识加密架构，服务器永不接触明文密码和解密密钥。

#### 1. 主密钥派生（Argon2id）

```python
from argon2 import PasswordHasher

# 参数配置（本地优化：降低内存和迭代以提升性能）
ph = PasswordHasher(
    memory_cost=65536,    # 64MB 内存（抗 GPU 攻击）
    time_cost=3,          # 3 次迭代
    parallelism=1,        # 1 并行度（本地优化）
    hash_len=32,          # 输出 32 字节
    salt_len=16           # 16 字节盐
)

# 派生主密钥
master_key = ph.hash(password=master_password, salt=user_email.encode())
```

**关键参数说明**：
- **memory_cost**：64MB（抗 GPU 暴力攻击，配合 Argon2id 内存困难特性）
- **time_cost**：3 次迭代（平衡性能和安全性）
- **parallelism**：1（本地单用户场景优化，减少并行开销）
- **salt**：使用用户邮箱作为盐（唯一性保证）

#### 2. 密钥扩展（HKDF-SHA256）

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# 扩展为 64 字节（32 字节加密密钥 + 32 字节 MAC 密钥）
hkdf = HKDF(
    algorithm=hashes.SHA256(),
    length=64,
    salt=None,
    info=b"keeper-v1-key-expansion"
)

expanded_key = hkdf.derive(master_key)
enc_key = expanded_key[:32]   # 前 32 字节用于 AES
mac_key = expanded_key[32:]   # 后 32 字节用于 HMAC（AES-GCM 自带认证，这里保留以便未来扩展）
```

#### 3. 数据加密（AES-256-GCM）

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64

# 初始化 AES-GCM
aesgcm = AESGCM(enc_key)

# 加密
nonce = os.urandom(12)  # 96-bit nonce（推荐）
ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), associated_data=None)

# 存储格式：nonce + ciphertext（GCM 的 tag 已包含在 ciphertext 中）
encrypted_data = base64.b64encode(nonce + ciphertext).decode()

# 解密
encrypted_bytes = base64.b64decode(encrypted_data)
nonce = encrypted_bytes[:12]
ciphertext = encrypted_bytes[12:]
plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None).decode()
```

#### 4. User Key 加密

```python
# 生成随机 User Key（用于加密 vault 数据）
user_key = os.urandom(32)

# 用 Master Key 加密 User Key
encrypted_user_key = aesgcm.encrypt(nonce, user_key, associated_data=None)

# 存储到 authentication 表
cursor.execute("""
    INSERT INTO authentication (id, email, encrypted_user_key, ...)
    VALUES (1, ?, ?, ...)
""", (user_email, base64.b64encode(encrypted_user_key).decode()))
```

### 加密数据存储格式

**accounts[].password 字段**：
```
格式：AES256GCM:<nonce>:<ciphertext>
示例：AES256GCM:r3d5f7h9j2k4m6n8:dGVzdGNpcGhlcnRleHQ...
```

**authentication.encrypted_user_key 字段**：
```
格式：Base64(<nonce> + <ciphertext>)
示例：c2FsdGVkX1+vupppZksvRf5pq5g5XjFRIipRkwB0K1Y=
```

### 加密流程

#### 用户注册
1. 客户端：从主密码派生 Master Key（Argon2id）
2. 客户端：扩展 Master Key（HKDF）
3. 客户端：生成随机 User Key
4. 客户端：用 Master Key 加密 User Key
5. 客户端：发送 `{ email, encrypted_user_key, kdf_params }` 到服务器
6. 服务器：存储到 `authentication` 表

#### 用户登录
1. 客户端：从主密码派生 Master Key
2. 客户端：从服务器获取 `encrypted_user_key`
3. 客户端：用 Master Key 解密得到 User Key
4. 客户端：用 User Key 解密所有 vault 数据

#### 数据加密
1. 客户端：用 User Key 加密密码字段
2. 客户端：发送加密后的 JSON 到服务器
3. 服务器：直接存储密文（无法解密）

---

## 安全层级说明

Keeper 采用三层防护 + 证书固定的安全架构：

### 第 1 层：自签名 HTTPS（传输加密）

**工具**：mkcert（本地 CA 证书生成）

```bash
# 安装 mkcert
# Arch Linux: sudo pacman -S mkcert
# Ubuntu: apt install mkcert

# 创建本地 CA
mkcert -install

# 生成 localhost 证书
mkcert localhost 127.0.0.1 ::1

# 输出：localhost.pem 和 localhost-key.pem
```

**FastAPI 配置**：
```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",         # 仅绑定回环地址
        port=8443,
        ssl_keyfile="./certs/localhost-key.pem",
        ssl_certfile="./certs/localhost.pem"
    )
```

**防护目标**：防止网络嗅探和中间人攻击

---

### 第 2 层：Localhost 绑定（网络隔离）

**配置**：仅监听 `127.0.0.1`，拒绝外部网络访问

```python
# ✅ 正确：只能本机访问
uvicorn.run(app, host="127.0.0.1", port=8443)

# ❌ 错误：局域网内所有设备可访问
uvicorn.run(app, host="0.0.0.0", port=8443)
```

**CORS 限制**：
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "moz-extension://YOUR_EXTENSION_ID"  # 仅允许扩展访问
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"]
)
```

**防护目标**：防止局域网内其他设备访问 API

---

### 第 3 层：客户端加密（数据保密）

**零知识架构**：
- 服务器只存储密文
- 解密密钥仅存在于客户端内存
- 主密码永不发送到服务器

**加密范围**：
- ✅ `accounts[].password`：完全加密
- ✅ `authentication.encrypted_user_key`：完全加密
- ❌ `name`, `urls`, `notes`：明文存储（便于搜索，可选择性加密）

**防护目标**：即使数据库泄露，攻击者无法解密密码

---

### 第 4 层：证书固定（防伪装攻击）

**场景**：防止本地恶意进程伪装成 Keeper API

**Firefox 扩展实现**：
```javascript
// keeper-firefox/src/background/security.ts

const EXPECTED_CERT_FINGERPRINT = "SHA256:YOUR_CERT_FINGERPRINT_HERE";

browser.webRequest.onHeadersReceived.addListener(
  async (details) => {
    try {
      const securityInfo = await browser.webRequest.getSecurityInfo(
        details.requestId,
        { certificateChain: false }
      );
      
      if (securityInfo.certificates[0].fingerprintSha256 !== EXPECTED_CERT_FINGERPRINT) {
        console.error("Certificate pinning failed! Possible attack detected.");
        return { cancel: true };  // 阻止请求
      }
    } catch (error) {
      console.error("Security check failed:", error);
      return { cancel: true };
    }
  },
  { urls: ["https://127.0.0.1:8443/*"] },
  ["blocking"]
);
```

**获取证书指纹**：
```bash
openssl x509 -in localhost.pem -noout -fingerprint -sha256
```

**防护目标**：防止本地 CA 污染或伪造证书攻击

---

### 安全威胁矩阵

| 威胁场景 | 第1层 HTTPS | 第2层 Localhost | 第3层 加密 | 第4层 证书固定 |
|---------|------------|----------------|----------|---------------|
| 网络嗅探（同局域网） | ✅ | ✅ | ✅ | - |
| 中间人攻击 | ✅ | N/A | ✅ | - |
| 恶意浏览器扩展窃听 | ❌ | ❌ | ✅ | - |
| 本地恶意进程伪装 API | ✅ | ❌ | ✅ | ✅ |
| 数据库文件泄露 | ❌ | ❌ | ✅ | - |
| 本地 CA 污染 | ❌ | ❌ | ✅ | ✅ |

---

## API 设计规范

### RESTful API 约定

**基础 URL**：`https://127.0.0.1:8443/api/v1`

**认证方式**：
- HTTP Header：`Authorization: Bearer <jwt_token>`
- 自定义头：`X-Keeper-Secret: <pre_shared_key>`（额外保护层）

**响应格式**：
```json
// 成功
{
  "success": true,
  "data": { ... }
}

// 失败
{
  "success": false,
  "error": {
    "code": "INVALID_PASSWORD",
    "message": "密码不正确"
  }
}
```

**分页格式**：
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 150,
    "page": 1,
    "pageSize": 20
  }
}
```

### 端点列表（待详细设计）

#### 认证相关
- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录
- `POST /api/v1/auth/logout` - 用户登出
- `POST /api/v1/auth/verify` - 验证 token

#### 书签管理
- `GET /api/v1/bookmarks` - 获取书签列表
- `GET /api/v1/bookmarks/:id` - 获取单个书签
- `POST /api/v1/bookmarks` - 创建书签
- `PUT /api/v1/bookmarks/:id` - 更新书签
- `DELETE /api/v1/bookmarks/:id` - 删除书签
- `GET /api/v1/bookmarks/search?q=<query>` - 搜索书签

#### 标签管理
- `GET /api/v1/tags` - 获取所有标签
- `POST /api/v1/tags` - 创建标签
- `PUT /api/v1/tags/:id` - 更新标签
- `DELETE /api/v1/tags/:id` - 删除标签（级联清理 bookmarks）

#### 关联管理
- `GET /api/v1/relations` - 获取所有关联
- `POST /api/v1/relations` - 创建关联
- `PUT /api/v1/relations/:id` - 更新关联
- `DELETE /api/v1/relations/:id` - 删除关联（级联清理 accounts）

---

## 项目关系

### 目录结构

```
~/workspace/projects/
├── keeper/                      # 后端 API（本项目）
│   ├── docs/
│   │   ├── schema.md            # 本文档
│   │   ├── api.md               # API 详细设计（待创建）
│   │   └── Phase1_Infrastructure_interaction_records.md
│   ├── src/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── models/              # SQLAlchemy 模型（待创建）
│   │   ├── routers/             # API 路由（待创建）
│   │   ├── crypto/              # 加密模块（待创建）
│   │   └── db/                  # 数据库连接（待创建）
│   ├── tests/                   # 测试（待创建）
│   ├── certs/                   # SSL 证书（mkcert 生成）
│   ├── pyproject.toml           # uv 依赖管理
│   └── README.md
│
└── keeper-firefox/              # 浏览器扩展
    ├── docs/
    │   ├── schema.md            # 数据库设计（与 keeper 同步）
    │   └── Phase1_Infrastructure_interaction_records.md
    ├── src/
    │   ├── popup/               # 弹出窗口（Vue 3）
    │   ├── background/          # 后台脚本（证书固定、API 调用）
    │   ├── content/             # 内容脚本（自动填充）
    │   └── composables/         # Vue 组合式函数
    ├── wxt.config.ts
    ├── package.json
    └── README.md
```

### 跨项目查询

**在 keeper 项目中查询 keeper-firefox**：
```bash
cd ~/workspace/projects/keeper
grep -r "某个功能" ../keeper-firefox/src/
```

**在 keeper-firefox 项目中查询 keeper**：
```bash
cd ~/workspace/projects/keeper-firefox
grep -r "某个 API" ../keeper/src/
```

**查看数据结构一致性**：
```bash
diff ~/workspace/projects/keeper/docs/schema.md \
     ~/workspace/projects/keeper-firefox/docs/schema.md
```

---

## 开发阶段规划

### 当前状态：Phase 1 - 基础设施

- ✅ 仓库初始化（keeper + keeper-firefox）
- ✅ 技术栈选型（FastAPI + Vue 3 + WXT）
- ✅ 数据库设计（schema.md）
- ⏳ API 设计（api.md）
- ⏳ 加密模块实现
- ⏳ HTTPS 证书配置

### 后续阶段

- **Phase 2**：后端核心（认证、CRUD、加密）
- **Phase 3**：前端核心（解锁 UI、vault 列表、搜索、键盘导航）
- **Phase 4**：核心场景（URL 打开、自动填充、快捷键）
- **Phase 5**：辅助功能（密码生成器、备份/导出）
- **Phase 6**：安全加固（内存清理、通信安全审计）

---

## 参考资料

### 技术文档
- [Bitwarden Security Whitepaper](https://bitwarden.com/help/bitwarden-security-white-paper/)
- [Argon2 RFC 9106](https://datatracker.ietf.org/doc/html/rfc9106)
- [HKDF RFC 5869](https://datatracker.ietf.org/doc/html/rfc5869)
- [AES-GCM NIST SP 800-38D](https://csrc.nist.gov/publications/detail/sp/800-38d/final)
- [mkcert - localhost HTTPS](https://github.com/FiloSottile/mkcert)
- [Firefox webRequest.getSecurityInfo()](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/getSecurityInfo)

### 依赖库
**后端（Python）**：
- `fastapi` - Web 框架
- `uvicorn[standard]` - ASGI 服务器
- `aiosqlite` - 异步 SQLite 驱动
- `argon2-cffi` - Argon2 密钥派生
- `cryptography` - AES-GCM 加密

**前端（TypeScript）**：
- `wxt` - 浏览器扩展框架
- `vue` - UI 框架
- `@vueuse/core` - Vue 工具集
- `motion` - 动画库

---

**最后更新**：2026-03-06  
**文档版本**：v1.0.0  
**维护者**：Keeper Development Team
