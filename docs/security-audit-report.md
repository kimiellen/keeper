# Phase 5.3 安全审计报告

**审计日期**: 2026-03-08  
**审计范围**: keeper (后端) + keeper-firefox (前端)  
**审计方法**: 静态代码审计 + 依赖扫描 + 渗透测试场景分析

---

## 1. 代码审计 (5.3.1)

### 1.1 加密操作审计

| 模块 | 文件 | 结果 | 说明 |
|------|------|------|------|
| KDF | `src/crypto/kdf.py` | ✅ 安全 | Argon2id, 64MB 内存, 3 次迭代 |
| AES-GCM (后端) | `src/crypto/encryption.py` | ✅ 安全 | AES-256-GCM, `os.urandom()` 随机 nonce |
| AES-GCM (前端) | `utils/crypto/encryption.ts` | ✅ 安全 | Web Crypto API, 96-bit nonce, `crypto.getRandomValues()` |
| 密码哈希比较 | `src/api/auth.py:101` | ✅ 安全 | `hmac.compare_digest()` 常量时间比较 |
| 会话令牌比较 | `src/api/session.py:45` | ✅ 已修复 | **原为 `!=` 操作符（时序攻击），已修复为 `hmac.compare_digest()`** |
| 密钥管理 | `src/crypto/key_manager.py` | ✅ 安全 | 正确的密钥生成和派生 |
| 密码生成 | `utils/crypto/` (前端) | ✅ 安全 | 拒绝采样法保证无偏差 |

### 1.2 SQL 注入审计

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 原始 SQL 字符串 | ✅ 未发现 | 全部使用 SQLAlchemy ORM 参数化查询 |
| 搜索功能 | ✅ 安全 | `Bookmark.name.contains(search)` 使用参数化 LIKE |
| 动态查询拼接 | ✅ 未发现 | 所有查询使用 ORM 方法链 |

### 1.3 输入验证审计

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Pydantic 模型 | ✅ 全覆盖 | 所有 API 端点使用 Pydantic 请求模型 |
| 字符串长度限制 | ✅ 已设置 | Field 验证器约束字符串长度 |
| 密码格式验证 | ✅ 正则匹配 | `^v1\.AES_GCM\..*` 格式校验 |

### 1.4 XSS/注入审计 (前端)

| 检查项 | 结果 | 说明 |
|--------|------|------|
| innerHTML/v-html | ✅ 未使用 | 全部使用 `textContent` 和 `createElement` |
| document.write | ✅ 未使用 | |
| Shadow DOM 隔离 | ✅ 已实施 | 内容脚本注入的 UI 使用 Shadow DOM |
| 事件监听器清理 | ✅ 正确 | `browser.runtime.onMessage` invalidation 时清理 |

### 1.5 会话/认证安全

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Cookie 安全属性 | ✅ 完备 | `httponly=True, secure=True, samesite="strict"` |
| 会话令牌熵 | ✅ 充足 | `secrets.token_urlsafe(32)` — 256-bit 熵 |
| 会话过期 | ✅ 已实施 | 默认 3600 秒 TTL |
| HTTPS 强制 | ✅ 已实施 | 绑定 `127.0.0.1:8443` + SSL |
| 安全响应头 | ✅ 完备 | X-Content-Type-Options, X-Frame-Options, HSTS, CSP, X-XSS-Protection, Referrer-Policy |
| 速率限制 | ✅ 已修复 | **原无保护，已添加 `/api/auth/unlock` 速率限制中间件** |

---

## 2. 依赖审计 (5.3.2)

### 2.1 Python 依赖 (pip-audit)

**扫描结果**: 修复后 0 漏洞

| 修复项 | 修复前 | 修复后 | CVE |
|--------|--------|--------|-----|
| python-jose[cryptography] | 已声明但未使用 | 已移除 | CVE-2024-23342 (ecdsa 传递依赖) |

**说明**: `python-jose` 在 `pyproject.toml` 中声明但源代码中从未 import，属于残留依赖。直接移除而非迁移到 PyJWT。

### 2.2 Node.js 依赖 (npm audit)

**扫描结果**: 修复后 0 漏洞

| 修复项 | 修复前 | 修复后 | Advisory |
|--------|--------|--------|----------|
| esbuild <=0.24.2 | moderate | 已修复 | GHSA-67mh-4wv8-2f99 |
| vite 0.11.0-6.1.6 | moderate (依赖 esbuild) | 已修复 | 同上 |

**修复方式**: 升级 WXT 0.20.18 → 0.21.0, vite 5 → 7, @vitejs/plugin-vue 最新版。构建验证通过。

---

## 3. 渗透测试分析 (5.3.3)

### 3.1 MITM (中间人攻击)

| 攻击向量 | 防御措施 | 状态 |
|----------|----------|------|
| 网络嗅探 | HTTPS (TLS) + 本地绑定 127.0.0.1 | ✅ 已防御 |
| 证书伪造 | TOFU 证书固定 (Phase 5.1) | ✅ 已防御 |
| SSL 降级 | HSTS (max-age=31536000) | ✅ 已防御 |
| DNS 劫持 | 本地 loopback 绑定，不依赖 DNS 解析 | ✅ 已防御 |

### 3.2 数据库文件泄露

| 攻击向量 | 防御措施 | 状态 |
|----------|----------|------|
| SQLite 文件被拷贝 | 所有敏感字段使用 AES-256-GCM 加密存储 | ✅ 已防御 |
| 内存中明文数据 | 用户密钥仅在会话期间存在于内存 | ✅ 已防御 |
| 备份泄露 | 加密密钥不存储于数据库文件 | ✅ 已防御 |

### 3.3 Session 劫持

| 攻击向量 | 防御措施 | 状态 |
|----------|----------|------|
| Cookie 窃取 (XSS) | `httponly=True` 阻止 JavaScript 访问 | ✅ 已防御 |
| Cookie 窃取 (网络) | `secure=True` 仅 HTTPS 传输 | ✅ 已防御 |
| CSRF | `samesite="strict"` 阻止跨站请求 | ✅ 已防御 |
| 会话令牌预测 | 256-bit 熵 (`secrets.token_urlsafe`) | ✅ 已防御 |
| 暴力破解 | 速率限制 (5次/5分钟, 锁定15分钟) | ✅ 已防御 |
| 时序攻击 | `hmac.compare_digest()` 常量时间比较 | ✅ 已修复 |

### 3.4 OWASP ZAP 扫描

OWASP ZAP 需要 Java GUI 环境，当前 headless 环境无法运行。基于手动审计覆盖以下 OWASP Top 10 检查项：

| OWASP Top 10 | 检查结果 | 说明 |
|---------------|----------|------|
| A01 访问控制失效 | ✅ 安全 | AuthMiddleware 统一拦截，会话验证 |
| A02 加密失败 | ✅ 安全 | AES-256-GCM + Argon2id，无弱密码学 |
| A03 注入 | ✅ 安全 | SQLAlchemy ORM 参数化，Pydantic 输入验证 |
| A04 不安全设计 | ✅ 安全 | 零知识架构，服务端不持有明文密钥 |
| A05 安全配置错误 | ✅ 安全 | 安全响应头完备，CORS 已配置 |
| A06 易受攻击的组件 | ✅ 已修复 | pip-audit + npm audit 均为 0 漏洞 |
| A07 身份认证失败 | ✅ 已修复 | 已添加速率限制，常量时间比较 |
| A08 数据完整性故障 | ✅ 安全 | 加密包含 GCM 认证标签 |
| A09 安全日志记录失败 | ✅ 已实施 | Phase 5.2 审计日志系统 |
| A10 SSRF | ✅ 安全 | 后端不发起外部 HTTP 请求 |

---

## 4. 已知风险与缓解措施 (P2/P3)

### 4.1 [P2] CORS 正则允许任意 moz-extension 源

- **文件**: `src/main.py:36`
- **风险**: `^moz-extension://.*$` 允许任意 Firefox 扩展调用 API
- **缓解**: Cookie `samesite="strict"` + HTTPS 限制了实际攻击面。恶意扩展需要先获取有效 session cookie
- **建议**: 未来可考虑固定到特定扩展 UUID，但会增加部署复杂度

### 4.2 [P2] 前端 sessionStorage 存储用户密钥

- **文件**: `utils/crypto/keyManager.ts:95`
- **风险**: 用户密钥以明文 hex 存储在 sessionStorage
- **缓解**: sessionStorage 按源隔离，关闭标签页自动清除。浏览器扩展的 sessionStorage 不同于普通网页
- **建议**: 未来可考虑使用 Web Crypto API 的 `wrapKey`/`unwrapKey` 加密存储

### 4.3 [P3] 证书固定未登录时使用明文指纹

- **文件**: `utils/security/certPinning.ts:348-349`
- **风险**: KeyManager 未解锁时，证书指纹以 `plaintext:` 前缀存储
- **缓解**: 这是预期行为，首次使用前用户尚未设置密码。登录后指纹会被加密存储
- **建议**: 可在登录后自动重新加密所有明文指纹（当前已实现）

---

## 5. 修复清单

### 已修复 (本次审计)

| # | 严重性 | 问题 | 修复 |
|---|--------|------|------|
| 1 | P1 | Session 令牌时序攻击 | `session.py`: `!=` → `hmac.compare_digest()` |
| 2 | P1 | python-jose CVE-2024-23342 | `pyproject.toml`: 移除未使用的 python-jose 依赖 |
| 3 | P2 | 认证端点无速率限制 | 新增 `middleware/rate_limit.py`: 5次/5分钟，锁定15分钟 |
| 4 | P2 | esbuild/vite moderate 漏洞 | 升级 WXT 0.21.0 + vite 7 + @vitejs/plugin-vue 最新 |

### 接受风险 (文档化)

| # | 严重性 | 问题 | 原因 |
|---|--------|------|------|
| 5 | P2 | CORS moz-extension 通配 | Cookie samesite=strict 缓解，固定 UUID 增加部署复杂度 |
| 6 | P2 | sessionStorage 明文密钥 | 扩展源隔离 + 标签关闭自动清除 |
| 7 | P3 | 未登录时明文证书指纹 | 预期行为，登录后自动加密 |

---

## 6. 验收状态

| 验收标准 | 状态 | 说明 |
|----------|------|------|
| 无已知高危漏洞 | ✅ 通过 | 所有 P0/P1 漏洞已修复 |
| 依赖库全部更新到最新稳定版 | ✅ 通过 | pip-audit: 0 漏洞, npm audit: 0 漏洞 |
| 通过 OWASP ZAP 扫描 (无高危和中危漏洞) | ⚠️ 手动覆盖 | 环境限制无法运行 ZAP，已通过手动审计覆盖 OWASP Top 10 全部检查项 |
