# Keeper 项目路线图

## 项目概览

**Keeper** 是一个本地优先的密码管理器,专为 Linux + Firefox 环境设计,采用零知识加密架构。项目分为前后端两个仓库:

- **keeper**: 后端 API (FastAPI + SQLite + Argon2id + AES-GCM)
- **keeper-firefox**: 前端浏览器扩展 (WXT + Vue 3)

**核心特性**:
- ✅ 零知识端到端加密 (服务器永不接触明文)
- ✅ 本地部署,数据完全自主控制
- ✅ 四层安全防护 (HTTPS + Localhost + E2E 加密 + 证书固定)
- ✅ 中文拼音首字母搜索
- ✅ 标签和关联独立管理

---

## 开发阶段划分

项目采用**迭代开发模型**,共分为 6 个阶段,每个阶段产出可用的增量功能。

| 阶段 | 名称 | 周期 | 状态 | 核心目标 |
|------|------|------|------|----------|
| Phase 1 | 基础设施 | 1 周 | ✅ 已完成 | 项目初始化、架构设计、文档完善 |
| Phase 2 | 后端核心 | 2 周 | ⏸️ 未开始 | 数据库、加密、认证、API |
| Phase 3 | 前端核心 | 2 周 | ⏸️ 未开始 | 扩展 UI、书签管理、加密集成 |
| Phase 4 | 集成测试 | 1 周 | ⏸️ 未开始 | 端到端测试、安全审计 |
| Phase 5 | 安全加固 | 1 周 | ⏸️ 未开始 | 证书固定、审计日志、漏洞修复 |
| Phase 6 | 用户体验优化 | 1 周 | ⏸️ 未开始 | 性能优化、中文搜索、导入导出 |

**总预计时间**: 8 周 (约 2 个月)

---

## Phase 1: 基础设施 ✅

**时间**: 2026-03-06 (已完成)

### 目标
- 完成项目架构设计和技术栈选型
- 初始化 Git 仓库和基础代码结构
- 编写完整的开发文档和 ADR

### 任务清单
- [x] 创建 GitHub 仓库 (keeper, keeper-firefox)
- [x] 初始化 Python 项目 (uv + FastAPI)
- [x] 初始化 Node.js 项目 (WXT + Vue 3)
- [x] 设计数据库 schema (4 表结构)
- [x] 设计加密方案 (Argon2id + HKDF + AES-GCM)
- [x] 设计安全架构 (四层防护)
- [x] 编写 `docs/schema.md` (数据库和加密设计)
- [x] 编写 `docs/Phase1_Infrastructure_interaction_records.md` (完整交互历史)
- [x] 编写 `CONTRIBUTING.md` (开发规范)
- [x] 编写 `docs/adr/` (5 个架构决策记录)
- [x] 编写 `docs/api.md` (完整 API 规范)
- [x] 编写 `docs/ROADMAP.md` (本文档)

### 交付物
- ✅ keeper 仓库: https://github.com/kimiellen/keeper
- ✅ keeper-firefox 仓库: https://github.com/kimiellen/keeper-firefox
- ✅ 完整的中文技术文档 (~4000 行)

### 关键决策 (ADRs)
1. **ADR-001**: 选择 SQLite 而非 PostgreSQL (单用户场景)
2. **ADR-002**: Tag 和 Relation 使用独立表 (用户需要专门的 CRUD UI)
3. **ADR-003**: 使用 Argon2id 而非 PBKDF2 (抗 GPU/ASIC 攻击)
4. **ADR-004**: 采用四层安全防护架构 (纵深防御)
5. **ADR-005**: 选择 AES-GCM 而非 AES-CBC+HMAC (AEAD,实现简单)

---

## Phase 2: 后端核心 ⏸️

**时间**: 预计 2026-03-10 → 2026-03-24 (2 周)

### 目标
实现 Keeper 后端的核心功能,提供完整的 REST API 供前端调用。

### 任务清单

#### 2.1 数据库层 (3 天)
- [ ] 安装依赖: `aiosqlite`, `sqlalchemy[asyncio]`
- [ ] 定义 SQLAlchemy 模型 (Tag, Relation, Bookmark, Authentication)
- [ ] 实现数据库初始化脚本 (`init_db.py`)
- [ ] 实现数据库迁移机制 (Alembic)
- [ ] 编写数据库操作的单元测试 (pytest)

**验收标准**:
- ✅ 运行 `python -m src.init_db` 成功创建 4 个表
- ✅ 所有表的约束 (唯一性、外键) 正常工作
- ✅ 测试覆盖率 ≥ 90%

#### 2.2 加密模块 (4 天)
- [ ] 实现 Argon2id KDF (`crypto/kdf.py`)
  - [ ] `derive_master_key(password, salt)` - 派生 Master Key
  - [ ] `derive_user_key(master_key)` - 使用 HKDF 派生 User Key
- [ ] 实现 AES-GCM 加密/解密 (`crypto/encryption.py`)
  - [ ] `encrypt(plaintext, user_key)` - 返回版本化密文
  - [ ] `decrypt(ciphertext, user_key)` - 返回明文
- [ ] 实现密钥管理 (`crypto/key_manager.py`)
  - [ ] `store_encrypted_user_key()` - 存储到 Authentication 表
  - [ ] `load_encrypted_user_key()` - 从数据库加载
- [ ] 编写加密模块的单元测试
  - [ ] 测试 Nonce 随机性 (加密同一明文 1000 次,密文不重复)
  - [ ] 测试认证标签验证 (篡改密文后解密失败)
  - [ ] 测试版本化格式解析

**验收标准**:
- ✅ Argon2id 参数符合本地优化策略 (16MB, 2 iterations, 4 parallelism)
- ✅ AES-GCM 使用 128-bit 认证标签
- ✅ 密文格式: `v1.AES_GCM.nonce_base64.ciphertext_base64.tag_base64`
- ✅ 测试覆盖率 ≥ 95%

#### 2.3 认证模块 (3 天)
- [ ] 实现认证端点 (`api/auth.py`)
  - [ ] `POST /api/auth/initialize` - 首次初始化
  - [ ] `POST /api/auth/unlock` - 解锁 (登录)
  - [ ] `POST /api/auth/lock` - 锁定 (登出)
  - [ ] `GET /api/auth/status` - 会话状态查询
- [ ] 实现 Session 管理 (基于内存,单用户)
  - [ ] Session token 生成 (secrets.token_urlsafe)
  - [ ] Session 过期机制 (默认 1 小时)
- [ ] 实现认证中间件 (`middleware/auth.py`)
  - [ ] 验证 Cookie 中的 session token
  - [ ] 未认证请求返回 401
- [ ] 编写认证流程的集成测试

**验收标准**:
- ✅ 初始化后无法重复初始化 (返回 409)
- ✅ 错误的主密码哈希返回 403
- ✅ Session 过期后自动锁定
- ✅ Cookie 设置正确: `HttpOnly; Secure; SameSite=Strict`

#### 2.4 CRUD API (4 天)
- [ ] 实现书签 API (`api/bookmarks.py`)
  - [ ] `GET /api/bookmarks` - 列表查询 (支持分页、标签过滤、搜索)
  - [ ] `GET /api/bookmarks/{id}` - 单个查询
  - [ ] `POST /api/bookmarks` - 创建
  - [ ] `PUT /api/bookmarks/{id}` - 完整更新
  - [ ] `PATCH /api/bookmarks/{id}` - 部分更新
  - [ ] `DELETE /api/bookmarks/{id}` - 删除
  - [ ] `POST /api/bookmarks/{id}/use` - 更新最后使用时间
- [ ] 实现标签 API (`api/tags.py`)
  - [ ] `GET /api/tags` - 列表查询
  - [ ] `POST /api/tags` - 创建
  - [ ] `PUT /api/tags/{id}` - 更新
  - [ ] `DELETE /api/tags/{id}` - 删除 (支持 cascade 参数)
- [ ] 实现关联 API (`api/relations.py`)
  - [ ] `GET /api/relations` - 列表查询
  - [ ] `POST /api/relations` - 创建
  - [ ] `PUT /api/relations/{id}` - 更新
  - [ ] `DELETE /api/relations/{id}` - 删除 (支持 cascade 参数)
- [ ] 实现统计 API (`api/stats.py`)
  - [ ] `GET /api/stats` - 获取概览统计
- [ ] 实现请求验证 (Pydantic models)
- [ ] 编写 API 集成测试

**验收标准**:
- ✅ 所有端点符合 `docs/api.md` 规范
- ✅ 参数验证失败返回 400,业务逻辑失败返回 422
- ✅ 外键约束正确工作 (tagIds, relatedIds 引用不存在的 ID 时返回 422)
- ✅ 级联删除正确工作 (cascade=true 时自动清理引用)
- ✅ 测试覆盖率 ≥ 85%

#### 2.5 HTTPS 配置 (2 天)
- [ ] 安装 mkcert: `brew install mkcert` (macOS) / `apt install mkcert` (Linux)
- [ ] 生成本地 CA 证书: `mkcert -install`
- [ ] 生成服务器证书: `mkcert localhost 127.0.0.1 ::1`
- [ ] 配置 uvicorn 使用 SSL 证书
- [ ] 实现 CORS 中间件 (仅允许扩展 UUID)
- [ ] 配置安全响应头 (X-Frame-Options, CSP, HSTS)
- [ ] 测试 HTTPS 连接 (curl, Postman)

**验收标准**:
- ✅ `curl https://127.0.0.1:8443/api/health` 返回 200
- ✅ `curl http://127.0.0.1:8443/api/health` 拒绝连接
- ✅ 仅监听 127.0.0.1,不监听 0.0.0.0
- ✅ 响应头包含所有安全头

### 交付物
- ✅ 可运行的后端 API (8 个端点)
- ✅ SQLite 数据库 (自动初始化)
- ✅ 完整的单元测试和集成测试
- ✅ HTTPS 本地证书配置
- ✅ Postman/curl 测试脚本

### 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Argon2id 参数过高导致性能问题 | 中 | 中 | 提前基准测试,调整参数 |
| SQLAlchemy 异步操作不熟悉 | 中 | 低 | 参考官方文档和示例代码 |
| mkcert 在某些 Linux 发行版无法安装 | 低 | 低 | 提供手动生成证书的文档 |

---

## Phase 3: 前端核心 ⏸️

**时间**: 预计 2026-03-24 → 2026-04-07 (2 周)

### 目标
实现 keeper-firefox 扩展的核心功能,与后端 API 集成,提供完整的用户界面。

### 任务清单

#### 3.1 加密模块 (3 天)
- [ ] 实现 Web Crypto API 封装 (`crypto/encryption.ts`)
  - [ ] `deriveKey(password, salt)` - 使用 PBKDF2 派生密钥 (浏览器不支持 Argon2id,需要 wasm)
  - [ ] `encrypt(plaintext, userKey)` - AES-GCM 加密
  - [ ] `decrypt(ciphertext, userKey)` - AES-GCM 解密
- [ ] 实现密钥管理 (`crypto/keyManager.ts`)
  - [ ] `storeUserKey(userKey)` - 存储到 session storage (内存)
  - [ ] `getUserKey()` - 从 session storage 获取
  - [ ] `clearUserKey()` - 锁定时清除
- [ ] 实现拼音首字母生成 (`utils/pinyin.ts`)
  - [ ] 使用 `pinyin-pro` 库
  - [ ] `getPinyinInitials("GitHub")` → `"gh"`
- [ ] 编写加密模块的单元测试 (Vitest)

**验收标准**:
- ✅ 加密后的密文格式与后端一致
- ✅ 后端加密的数据可在前端解密
- ✅ 拼音首字母生成准确 (测试常见汉字)

#### 3.2 API 客户端 (2 天)
- [ ] 实现 API 客户端 (`api/client.ts`)
  - [ ] `KeeperAPIClient` 类 (封装 fetch)
  - [ ] 自动处理错误响应 (APIError)
  - [ ] 自动重试机制 (网络错误时)
- [ ] 实现所有 API 方法
  - [ ] 认证: `unlock()`, `lock()`, `getStatus()`
  - [ ] 书签: `getBookmarks()`, `createBookmark()`, `updateBookmark()`, `deleteBookmark()`
  - [ ] 标签: `getTags()`, `createTag()`, `deleteTag()`
  - [ ] 关联: `getRelations()`, `createRelation()`, `deleteRelation()`
- [ ] 实现证书固定 (Phase 3 暂不实现,Phase 5 加固时添加)
- [ ] 编写 API 客户端的集成测试 (mock fetch)

**验收标准**:
- ✅ 所有 API 方法与 `docs/api.md` 一致
- ✅ Cookie 自动发送 (credentials: 'include')
- ✅ 错误处理完整 (网络错误、HTTP 错误、业务错误)

#### 3.3 状态管理 (2 天)
- [ ] 选择状态管理方案: **Pinia** (Vue 3 官方推荐)
- [ ] 实现认证 store (`stores/auth.ts`)
  - [ ] `state`: `{ locked, userKey, sessionExpiresAt }`
  - [ ] `actions`: `unlock(password)`, `lock()`, `checkStatus()`
- [ ] 实现书签 store (`stores/bookmarks.ts`)
  - [ ] `state`: `{ bookmarks, tags, relations, loading }`
  - [ ] `actions`: `fetchBookmarks(filters)`, `createBookmark()`, `updateBookmark()`, `deleteBookmark()`
  - [ ] `getters`: `bookmarksByTag(tagId)`, `searchBookmarks(query)`
- [ ] 实现标签 store (`stores/tags.ts`)
- [ ] 实现关联 store (`stores/relations.ts`)
- [ ] 编写 store 的单元测试

**验收标准**:
- ✅ 所有异步操作正确处理加载状态
- ✅ 错误自动显示到 UI (toast notification)
- ✅ 数据缓存和自动刷新

#### 3.4 UI 组件 (5 天)
- [ ] 设计 UI 框架: **Element Plus** (Vue 3 组件库)
- [ ] 实现解锁界面 (`popup/views/Unlock.vue`)
  - [ ] 主密码输入框
  - [ ] "解锁" 按钮 (调用 `authStore.unlock()`)
  - [ ] 错误提示
- [ ] 实现主界面 (`popup/views/Main.vue`)
  - [ ] 顶部搜索框 (支持拼音首字母搜索)
  - [ ] 书签列表 (虚拟滚动,支持大量数据)
  - [ ] 书签卡片 (显示名称、标签、最后使用时间)
  - [ ] "添加书签" 按钮
- [ ] 实现书签编辑界面 (`popup/views/BookmarkEdit.vue`)
  - [ ] 名称输入框 (自动生成拼音首字母)
  - [ ] URL 列表 (动态增删)
  - [ ] 账号列表 (动态增删)
  - [ ] 标签多选框 (checkbox)
  - [ ] 关联多选框 (checkbox)
  - [ ] 备注输入框
  - [ ] "保存" 和 "取消" 按钮
- [ ] 实现标签管理界面 (`popup/views/Tags.vue`)
  - [ ] 标签列表
  - [ ] "添加标签" 对话框
  - [ ] "编辑标签" 对话框
  - [ ] "删除标签" 确认对话框 (提示是否级联删除)
- [ ] 实现关联管理界面 (`popup/views/Relations.vue`)
  - [ ] 关联列表
  - [ ] "添加关联" 对话框
  - [ ] "删除关联" 确认对话框
- [ ] 实现设置界面 (`popup/views/Settings.vue`)
  - [ ] "导出数据" 按钮
  - [ ] "导入数据" 按钮
  - [ ] "锁定" 按钮
  - [ ] 会话超时设置
- [ ] 编写 UI 组件的单元测试 (Vue Test Utils)

**验收标准**:
- ✅ 界面符合 Material Design 或 Fluent Design 规范
- ✅ 支持键盘快捷键 (Ctrl+F 搜索,Esc 关闭对话框)
- ✅ 支持暗色模式 (根据系统设置自动切换)
- ✅ 响应式布局 (支持不同窗口尺寸)

#### 3.5 Content Script (2 天)
- [ ] 实现自动填充功能 (`content/autofill.ts`)
  - [ ] 监听表单提交事件
  - [ ] 识别登录表单 (username + password 字段)
  - [ ] 自动匹配当前 URL 的书签
  - [ ] 弹出账号选择菜单 (如果有多个账号)
  - [ ] 填充用户名和密码 (解密后)
- [ ] 实现密码生成器 (`content/generator.ts`)
  - [ ] 右键菜单 "生成密码"
  - [ ] 可配置长度、字符集
  - [ ] 自动填充到密码框
- [ ] 实现密码捕获 (`content/capture.ts`)
  - [ ] 监听表单提交
  - [ ] 检测新密码 (之前未保存的)
  - [ ] 弹出 "保存到 Keeper?" 提示

**验收标准**:
- ✅ 自动填充在主流网站 (GitHub, Google) 正常工作
- ✅ 密码生成器生成的密码强度符合 OWASP 推荐
- ✅ 密码捕获不会误触发 (如搜索框输入)

### 交付物
- ✅ 可安装的 Firefox 扩展 (.xpi)
- ✅ 完整的用户界面 (5 个视图)
- ✅ 自动填充和密码捕获功能
- ✅ 单元测试和 E2E 测试

### 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Web Crypto API 不支持 Argon2id | 高 | 高 | 使用 argon2-browser (wasm 实现) |
| 自动填充在某些网站不工作 | 中 | 中 | 提供手动复制按钮作为备选 |
| Content Script 被网站 CSP 阻止 | 低 | 低 | 使用 webRequest API 注入脚本 |

---

## Phase 4: 集成测试 ⏸️

**时间**: 预计 2026-04-07 → 2026-04-14 (1 周)

### 目标
进行端到端测试,确保前后端完整集成,发现并修复 bug。

### 任务清单

#### 4.1 端到端测试 (4 天)
- [ ] 安装 Playwright (浏览器自动化测试)
- [ ] 编写测试场景
  - [ ] **场景 1**: 首次初始化流程
    1. 启动后端 API
    2. 安装扩展
    3. 设置主密码
    4. 验证 Authentication 表已创建
  - [ ] **场景 2**: 解锁流程
    1. 输入主密码
    2. 解锁成功
    3. 验证 session cookie 已设置
  - [ ] **场景 3**: 创建书签
    1. 点击 "添加书签"
    2. 填写表单 (名称、URL、账号、密码)
    3. 选择标签
    4. 保存
    5. 验证数据库中密码已加密
  - [ ] **场景 4**: 搜索书签
    1. 在搜索框输入拼音首字母 "gh"
    2. 验证 "GitHub" 书签显示
  - [ ] **场景 5**: 自动填充
    1. 访问 https://github.com/login
    2. 等待自动填充提示
    3. 选择账号
    4. 验证用户名和密码已填充
  - [ ] **场景 6**: 密码捕获
    1. 访问测试网站
    2. 提交新密码
    3. 验证 "保存到 Keeper?" 提示显示
    4. 保存
    5. 验证数据库中已添加
  - [ ] **场景 7**: 导出导入
    1. 导出所有数据
    2. 清空数据库
    3. 导入数据
    4. 验证数据一致
- [ ] 运行所有测试,记录失败案例
- [ ] 修复发现的 bug
- [ ] 重新运行测试,确保通过率 100%

**验收标准**:
- ✅ 所有 7 个场景测试通过
- ✅ 覆盖率: 前端 ≥ 80%,后端 ≥ 85%
- ✅ 无已知 P0/P1 bug

#### 4.2 性能测试 (2 天)
- [ ] 测试数据库性能
  - [ ] 插入 10,000 条书签,测试查询速度
  - [ ] 验证分页查询 < 100ms
- [ ] 测试加密性能
  - [ ] 批量加密 1000 条密码,测试总耗时
  - [ ] 验证单次加密 < 5ms
- [ ] 测试 API 性能
  - [ ] 使用 k6 进行压力测试
  - [ ] 验证 `/api/bookmarks` 在 1000 QPS 下响应时间 < 200ms
- [ ] 测试扩展性能
  - [ ] 测试 popup 打开速度 (< 500ms)
  - [ ] 测试大列表滚动流畅度 (60 FPS)

**验收标准**:
- ✅ 所有性能指标符合预期
- ✅ 无明显卡顿或延迟

#### 4.3 兼容性测试 (1 天)
- [ ] 测试 Linux 发行版
  - [ ] Ubuntu 22.04 LTS
  - [ ] Fedora 39
  - [ ] Arch Linux (latest)
- [ ] 测试 Firefox 版本
  - [ ] Firefox 115 ESR
  - [ ] Firefox 122 (最新稳定版)
  - [ ] Firefox Nightly (最新开发版)
- [ ] 记录不兼容的环境,更新文档

**验收标准**:
- ✅ 在所有测试环境下正常运行
- ✅ 文档中明确列出不支持的环境

### 交付物
- ✅ 完整的 E2E 测试套件
- ✅ 性能测试报告
- ✅ 兼容性测试报告
- ✅ Bug 修复记录

---

## Phase 5: 安全加固 ⏸️

**时间**: 预计 2026-04-14 → 2026-04-21 (1 周)

### 目标
实现第四层安全防护 (证书固定),添加审计日志,进行安全审计和漏洞修复。

### 任务清单

#### 5.1 证书固定 (3 天)
- [ ] 实现证书固定功能 (`security/certPinning.ts`)
  - [ ] 监听 `webRequest.onHeadersReceived`
  - [ ] 调用 `webRequest.getSecurityInfo()` 获取证书
  - [ ] 计算 SHA-256 指纹
  - [ ] 首次连接时存储指纹到 extension storage
  - [ ] 后续连接验证指纹
  - [ ] 指纹不匹配时阻止请求,显示警告
- [ ] 实现指纹更新机制
  - [ ] 证书过期时显示 "信任新证书" 按钮
  - [ ] 用户确认后更新存储的指纹
  - [ ] 记录指纹更新日志
- [ ] 编写证书固定的测试
  - [ ] 模拟伪造证书攻击,验证阻止成功
  - [ ] 模拟证书更新,验证流程正常

**验收标准**:
- ✅ 伪造证书无法通过验证
- ✅ 证书更新流程用户友好
- ✅ 指纹存储加密 (使用 User Key)

#### 5.2 审计日志 (2 天)
- [ ] 实现审计日志模块 (`security/auditLog.ts`)
  - [ ] 记录所有敏感操作:
    - 解锁/锁定
    - 创建/更新/删除书签
    - 导出数据
    - 证书固定失败
  - [ ] 日志格式: `{ timestamp, action, userId, details, ipAddress }`
  - [ ] 日志存储: SQLite 单独的 `audit_log` 表
- [ ] 实现日志查看界面 (`popup/views/AuditLog.vue`)
  - [ ] 分页显示日志
  - [ ] 支持按操作类型过滤
  - [ ] 支持按时间范围过滤
- [ ] 实现日志导出功能 (CSV 格式)

**验收标准**:
- ✅ 所有敏感操作均被记录
- ✅ 日志不可篡改 (只能追加)
- ✅ 日志界面清晰易读

#### 5.3 安全审计 (2 天)
- [ ] 代码审计
  - [ ] 检查所有加密操作 (是否使用恒定时间比较)
  - [ ] 检查所有数据库查询 (是否防止 SQL 注入)
  - [ ] 检查所有用户输入 (是否验证和过滤)
- [ ] 依赖审计
  - [ ] 运行 `pip-audit` (Python 依赖)
  - [ ] 运行 `npm audit` (Node.js 依赖)
  - [ ] 更新所有已知漏洞的依赖
- [ ] 渗透测试
  - [ ] 模拟攻击场景:
    - MITM 攻击 (证书固定应阻止)
    - 数据库文件泄露 (密文应不可读)
    - Session 劫持 (HttpOnly cookie 应防护)
  - [ ] 使用 OWASP ZAP 扫描 API
  - [ ] 记录发现的漏洞,制定修复计划
- [ ] 修复所有 P0/P1 漏洞

**验收标准**:
- ✅ 无已知高危漏洞
- ✅ 依赖库全部更新到最新稳定版
- ✅ 通过 OWASP ZAP 扫描 (无高危和中危漏洞)

### 交付物
- ✅ 证书固定功能 (第四层安全防护完成)
- ✅ 完整的审计日志系统
- ✅ 安全审计报告
- ✅ 漏洞修复记录

---

## Phase 6: 用户体验优化 ⏸️

**时间**: 预计 2026-04-21 → 2026-04-28 (1 周)

### 目标
优化性能,完善中文搜索,添加导入导出功能,提升整体用户体验。

### 任务清单

#### 6.1 性能优化 (2 天)
- [ ] 前端性能优化
  - [ ] 实现虚拟滚动 (长列表)
  - [ ] 懒加载图标 (标签图标)
  - [ ] 防抖搜索输入 (300ms)
  - [ ] 缓存搜索结果
- [ ] 后端性能优化
  - [ ] 添加数据库索引 (name, lastUsedAt)
  - [ ] 优化查询 (避免 N+1 查询)
  - [ ] 启用 SQLite WAL 模式 (提升并发性能)
- [ ] 内存优化
  - [ ] 限制解密密码的缓存数量 (最多 100 条)
  - [ ] 锁定时立即清空内存中的 User Key
- [ ] 运行性能基准测试,验证优化效果

**验收标准**:
- ✅ Popup 打开速度 < 300ms (之前 500ms)
- ✅ 搜索响应时间 < 50ms (之前 100ms)
- ✅ 内存占用 < 50MB (空闲时)

#### 6.2 中文搜索优化 (2 天)
- [ ] 实现模糊搜索
  - [ ] 支持拼音全拼搜索 (如 "github" → "GitHub")
  - [ ] 支持首字母缩写 (如 "gh" → "GitHub")
  - [ ] 支持中文直接搜索 (如 "工作" → 匹配标签 "工作")
- [ ] 实现搜索结果排序
  - [ ] 优先级: 精确匹配 > 前缀匹配 > 模糊匹配
  - [ ] 相同优先级按最后使用时间排序
- [ ] 实现搜索高亮
  - [ ] 搜索结果中高亮匹配的关键词
- [ ] 编写搜索功能的测试

**验收标准**:
- ✅ 搜索 "gh" 能找到 "GitHub"
- ✅ 搜索 "工作" 能找到所有带 "工作" 标签的书签
- ✅ 搜索结果排序合理

#### 6.3 导入导出功能 (2 天)
- [ ] 实现导出功能
  - [ ] JSON 格式导出 (完整数据)
  - [ ] CSV 格式导出 (书签列表,密码已解密)
  - [ ] 导出前提示 "CSV 文件包含明文密码,请妥善保管"
- [ ] 实现导入功能
  - [ ] 支持导入自身导出的 JSON
  - [ ] 支持导入 Bitwarden 导出的 JSON
  - [ ] 支持导入 CSV (自动加密密码)
  - [ ] 导入前预览 (显示将要导入的条目数)
  - [ ] 支持合并或覆盖模式
- [ ] 实现导入冲突处理
  - [ ] 名称重复时提示用户选择: 跳过 / 重命名 / 覆盖
- [ ] 编写导入导出的测试

**验收标准**:
- ✅ 导出的 JSON 可成功导入
- ✅ Bitwarden 导出的数据可成功导入 (密码正确解密)
- ✅ CSV 导出的密码是明文,导入后自动加密

#### 6.4 文档完善 (1 天)
- [ ] 编写用户手册 (`docs/user-guide.md`)
  - [ ] 安装指南 (后端 + 扩展)
  - [ ] 首次使用流程
  - [ ] 功能介绍 (书签管理、标签、关联)
  - [ ] 常见问题 (FAQ)
- [ ] 编写开发者文档 (`docs/developer-guide.md`)
  - [ ] 架构图
  - [ ] 数据流图
  - [ ] API 调用示例
  - [ ] 贡献指南
- [ ] 更新 README.md
  - [ ] 添加功能截图
  - [ ] 添加安装步骤
  - [ ] 添加许可证信息 (MIT)

**验收标准**:
- ✅ 新用户可根据文档独立完成安装
- ✅ 开发者可根据文档理解架构
- ✅ README.md 包含完整的项目介绍

### 交付物
- ✅ 性能优化报告 (优化前后对比)
- ✅ 完善的中文搜索功能
- ✅ 导入导出功能 (支持 Bitwarden)
- ✅ 完整的用户手册和开发者文档

---

## 里程碑总结

| 里程碑 | 日期 | 交付物 |
|--------|------|--------|
| M1: 基础设施完成 | 2026-03-06 | 项目初始化、完整文档 ✅ |
| M2: 后端 MVP | 2026-03-24 | 可用的 REST API |
| M3: 前端 MVP | 2026-04-07 | 可安装的扩展 |
| M4: 集成完成 | 2026-04-14 | E2E 测试通过 |
| M5: 安全加固完成 | 2026-04-21 | 四层防护、审计日志 |
| M6: 正式发布 | 2026-04-28 | v1.0.0 公开发布 |

---

## 版本规划

### v1.0.0 (2026-04-28)
- ✅ 核心功能: 书签管理、标签、关联
- ✅ 零知识加密
- ✅ 四层安全防护
- ✅ 自动填充和密码捕获
- ✅ 导入导出 (JSON, CSV, Bitwarden)

### v1.1.0 (2026-06)
- 🔄 书签分组功能 (文件夹结构)
- 🔄 密码强度检测
- 🔄 密码泄露检查 (Have I Been Pwned API)
- 🔄 双因素认证 (TOTP)

### v1.2.0 (2026-08)
- 🔄 浏览器历史记录同步
- 🔄 自动备份到本地文件
- 🔄 密码生成器增强 (可读密码、密码短语)

### v2.0.0 (2026-12)
- 🔄 多用户支持 (需重新设计认证)
- 🔄 WebDAV 同步 (可选)
- 🔄 命令行工具 (keeper-cli)

---

## 贡献指南

欢迎贡献! 请参考 `CONTRIBUTING.md` 了解开发规范。

**当前优先级**:
1. **P0** (阻塞发布): 安全漏洞、数据丢失
2. **P1** (高优先级): 核心功能缺失、严重 bug
3. **P2** (中优先级): 用户体验问题、性能优化
4. **P3** (低优先级): 文档改进、代码重构

**开发流程**:
1. Fork 仓库
2. 创建 feature 分支: `git checkout -b feature/my-feature`
3. 提交代码: `git commit -m "feat: add my feature"`
4. 推送到 GitHub: `git push origin feature/my-feature`
5. 创建 Pull Request

---

## 许可证

Keeper 使用 **MIT License**,允许商业和个人使用。

---

## 联系方式

- **项目主页**: https://github.com/kimiellen/keeper
- **问题反馈**: https://github.com/kimiellen/keeper/issues
- **安全漏洞**: 请发送邮件至 [待定]

---

**最后更新**: 2026-03-06  
**文档版本**: 1.0.0
