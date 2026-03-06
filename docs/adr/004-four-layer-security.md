# ADR-004: 四层安全防护架构

## 状态
已接受

## 日期
2026-03-06

## 背景

Keeper 是一个本地密码管理器,采用零知识加密架构。虽然数据存储在本地,但在 Firefox 扩展与后端 API 通信过程中,仍需要防范以下威胁:

1. **网络嗅探攻击**: 即使在本地环回接口,理论上仍可能被恶意软件监听
2. **中间人攻击 (MITM)**: 恶意程序可能劫持本地 HTTP 流量
3. **证书伪造**: 攻击者可能生成伪造证书欺骗客户端
4. **数据库泄露**: 物理访问机器时数据库文件可能被窃取
5. **内存转储攻击**: 进程内存可能包含解密后的敏感数据

传统的单层防护(例如仅使用 HTTPS)在本地场景下可能存在以下问题:
- 自签名证书容易被用户忽略警告而接受伪造证书
- localhost 绑定可以被绕过(如修改 hosts 文件)
- 客户端加密可以被中间人在传输层拦截

因此需要设计多层防御体系,确保即使某一层被突破,其他层仍能提供保护。

## 决策

我们采用**四层安全防护架构**,每层独立运作,形成纵深防御:

### 第一层: HTTPS 传输加密

**目标**: 防止传输层数据被窃听和篡改

**实现方案**:
- 使用 `mkcert` 生成本地信任的 CA 证书和服务器证书
- 后端 FastAPI 强制使用 HTTPS (uvicorn `--ssl-keyfile` 和 `--ssl-certfile`)
- 禁用 HTTP 访问,不提供 HTTP → HTTPS 重定向(避免降级攻击)

**防护对象**: 
- 网络层嗅探(即使在 lo 接口)
- 明文传输拦截

**技术细节**:
```bash
# 生成证书
mkcert -install
mkcert localhost 127.0.0.1 ::1

# uvicorn 配置
uvicorn src.main:app \
  --host 127.0.0.1 \
  --port 8443 \
  --ssl-keyfile=certs/localhost+2-key.pem \
  --ssl-certfile=certs/localhost+2.pem
```

### 第二层: 网络隔离 (Localhost 绑定)

**目标**: 限制 API 访问范围,防止远程攻击

**实现方案**:
- 后端仅监听 `127.0.0.1:8443`,拒绝 `0.0.0.0` 绑定
- 防火墙规则明确禁止 8443 端口对外访问
- 扩展通过 `https://127.0.0.1:8443` 访问 API

**防护对象**:
- 局域网内的未授权访问
- 远程攻击者扫描端口
- 意外的公网暴露

**技术细节**:
```python
# FastAPI 启动配置
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",  # 仅本地访问
        port=8443,
        ssl_keyfile="certs/localhost+2-key.pem",
        ssl_certfile="certs/localhost+2.pem"
    )
```

### 第三层: 客户端端到端加密

**目标**: 即使 HTTPS 被破解,数据仍不可读

**实现方案**:
- 所有敏感数据(密码、备注)在扩展中加密后再发送
- 服务器仅存储密文,永不接触明文
- 加密密钥由主密码派生,仅存在于客户端内存

**防护对象**:
- 数据库文件泄露
- 服务器内存转储
- 传输层被突破后的数据窃取

**加密流程**:
```
用户主密码
    ↓ Argon2id (KDF)
Master Key (256-bit)
    ↓ HKDF (Key Expansion)
├─ User Key (256-bit) → 加密存储到 Authentication 表
└─ MAC Key (256-bit)  → 用于 HMAC 完整性校验

加密数据时:
明文 → AES-256-GCM(User Key, 随机 Nonce) → 密文 + Auth Tag → Base64 → 存储
```

**数据流示例**:
```javascript
// 扩展端加密
const plainPassword = "MySecret123!";
const encryptedPassword = await encryptWithUserKey(plainPassword);

// 发送到服务器
await fetch('https://127.0.0.1:8443/api/bookmarks', {
  method: 'POST',
  body: JSON.stringify({
    accounts: [{
      username: "user@example.com",
      password: encryptedPassword  // 已加密,服务器无法解密
    }]
  })
});

// 服务器仅存储密文
INSERT INTO bookmarks (accounts) VALUES (
  '[{"username":"user@example.com","password":"v1.AES_GCM.nonce_base64.ciphertext_base64.tag_base64"}]'
);
```

### 第四层: 证书固定 (Certificate Pinning)

**目标**: 防止伪造证书的中间人攻击

**实现方案**:
- 扩展在首次连接时获取服务器证书指纹
- 将 SHA-256 指纹存储到 extension storage
- 后续请求验证证书指纹是否匹配,不匹配则拒绝连接

**防护对象**:
- 伪造的自签名证书
- 被入侵的系统 CA
- 恶意代理服务器

**技术细节**:
```javascript
// 获取证书信息
browser.webRequest.onHeadersReceived.addListener(
  async (details) => {
    const securityInfo = await browser.webRequest.getSecurityInfo(
      details.requestId,
      { certificateChain: true }
    );
    
    // 计算证书指纹
    const cert = securityInfo.certificates[0];
    const fingerprint = await sha256(cert.rawDER);
    
    // 首次连接: 存储指纹
    const stored = await browser.storage.local.get('certFingerprint');
    if (!stored.certFingerprint) {
      await browser.storage.local.set({ certFingerprint: fingerprint });
      return;
    }
    
    // 后续连接: 验证指纹
    if (stored.certFingerprint !== fingerprint) {
      throw new Error('Certificate pinning failed! Possible MITM attack.');
    }
  },
  { urls: ['https://127.0.0.1:8443/*'] },
  ['blocking']
);
```

**指纹更新机制**:
- 证书过期重新生成时,扩展提供 "信任新证书" 按钮
- 用户确认后更新存储的指纹
- 记录指纹更新日志供审计

## 四层防护的协同作用

| 攻击场景 | 第一层 HTTPS | 第二层 Localhost | 第三层 E2E 加密 | 第四层 证书固定 | 结果 |
|---------|-------------|-----------------|----------------|----------------|------|
| 网络嗅探 | ✅ 阻止 | - | - | - | 安全 |
| 远程端口扫描 | - | ✅ 阻止 | - | - | 安全 |
| 伪造证书 MITM | ⚠️ 可能被绕过 | - | - | ✅ 阻止 | 安全 |
| HTTPS 被破解 | ❌ 失效 | - | ✅ 数据仍加密 | - | 安全 |
| 数据库文件被盗 | ❌ 无保护 | ❌ 无保护 | ✅ 密文不可读 | - | 安全 |
| 内存转储攻击 | ❌ 无保护 | ❌ 无保护 | ⚠️ 运行时明文 | - | 有限保护* |

\* 内存转储攻击需要额外的运行时保护措施(如内存加密、进程隔离),不在本 ADR 范围内。

## 防御层级示意图

```
┌─────────────────────────────────────────────────────────────┐
│                     Firefox Extension                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 第四层: 证书固定验证                                     │  │
│  │ - 验证服务器证书指纹                                     │  │
│  │ - 检测伪造证书                                          │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 第三层: 客户端加密                                      │  │
│  │ - 加密敏感数据 (AES-GCM)                               │  │
│  │ - 永不发送明文密码                                      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS (加密通道)
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Keeper Backend API                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 第一层: HTTPS 传输加密                                   │  │
│  │ - TLS 1.3 协议                                         │  │
│  │ - mkcert 本地 CA 证书                                   │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 第二层: 网络隔离                                        │  │
│  │ - 仅监听 127.0.0.1:8443                                │  │
│  │ - 拒绝远程连接                                          │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 数据层: 仅存储密文                                      │  │
│  │ - SQLite 存储加密数据                                   │  │
│  │ - 服务器永不解密                                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 与其他方案的对比

### 方案 A: 仅使用 HTTPS
- ✅ 简单易实现
- ❌ 自签名证书容易被伪造
- ❌ 数据库泄露后无保护
- **适用场景**: 信任网络环境的场景

### 方案 B: HTTPS + 客户端加密 (两层)
- ✅ 提供基本的端到端保护
- ❌ 无法防御伪造证书攻击
- ❌ 未限制网络访问范围
- **适用场景**: 中等安全要求的应用

### 方案 C: 四层防护 (本方案)
- ✅ 纵深防御,单点失效不影响整体安全
- ✅ 覆盖传输层、网络层、应用层威胁
- ✅ 零知识架构,服务器端完全不可信
- ⚠️ 实现复杂度较高
- **适用场景**: 高安全要求的密码管理器

### 方案 D: 四层 + 硬件安全模块 (HSM/TPM)
- ✅ 提供硬件级密钥保护
- ✅ 防御内存转储攻击
- ❌ 需要硬件支持,跨平台困难
- ❌ 大幅增加复杂度
- **适用场景**: 企业级密钥管理系统

**决策理由**: 
- 方案 C 在实现复杂度和安全性之间取得最佳平衡
- 适合单用户本地部署场景
- 可在未来需要时升级到方案 D

## 实现优先级

### Phase 2 (必须实现)
1. ✅ 第一层: HTTPS 配置 (mkcert + uvicorn SSL)
2. ✅ 第二层: localhost 绑定 (host="127.0.0.1")
3. ✅ 第三层: 基础加密 (Argon2id + AES-GCM)

### Phase 3 (推荐实现)
4. 🔄 第四层: 证书固定 (webRequest.getSecurityInfo)

### 未来增强 (可选)
5. 运行时内存保护 (自动清零敏感数据)
6. 审计日志 (记录所有安全事件)
7. 异常检测 (识别可疑的访问模式)

## 安全性分析

### 威胁模型覆盖度

| 威胁类型 | STRIDE 分类 | 是否防护 | 防护层 |
|---------|------------|---------|-------|
| 网络嗅探 | Information Disclosure | ✅ | 第一层 |
| 远程攻击 | Elevation of Privilege | ✅ | 第二层 |
| 证书伪造 | Spoofing | ✅ | 第四层 |
| 数据库泄露 | Information Disclosure | ✅ | 第三层 |
| 数据篡改 | Tampering | ✅ | 第三层 (GCM Auth Tag) |
| 重放攻击 | Replay | ⚠️ | 部分 (Nonce)* |
| 拒绝服务 | Denial of Service | ❌ | 不适用** |

\* 重放攻击通过 AES-GCM 的随机 Nonce 部分缓解,完整防护需要请求签名(未实现)  
\*\* 本地单用户场景下 DoS 攻击无实际意义

### 残留风险

以下风险**不在本架构防护范围内**,需要通过其他手段缓解:

1. **物理访问攻击**: 
   - 攻击者物理访问机器时可能通过键盘记录器窃取主密码
   - 缓解措施: 依赖操作系统的磁盘加密和屏幕锁定

2. **浏览器扩展漏洞**:
   - Firefox 本身的漏洞可能导致扩展沙箱逃逸
   - 缓解措施: 及时更新 Firefox,启用自动更新

3. **供应链攻击**:
   - 依赖库(如 argon2-cffi)可能被植入后门
   - 缓解措施: 锁定依赖版本,使用 `pip-audit` 检查已知漏洞

4. **侧信道攻击**:
   - 时间侧信道、功耗分析等高级攻击
   - 缓解措施: 使用恒定时间比较函数,不在本 ADR 范围内

## 性能影响

### HTTPS 开销
- TLS 握手: 首次连接 +50-100ms (后续复用连接)
- 加密开销: < 1% CPU (AES-NI 硬件加速)
- **影响评估**: 可忽略

### 证书固定开销
- 证书验证: 每次请求 +5-10ms (SHA-256 计算)
- **影响评估**: 可接受,用户无感知

### 客户端加密开销
- Argon2id KDF: 首次解锁 ~2 秒 (单次)
- AES-GCM 加密: 每条密码 < 1ms
- **影响评估**: 符合预期,安全性收益远大于性能损失

## 运维考虑

### 证书管理
- **有效期**: mkcert 生成的证书默认 10 年
- **更新流程**: 证书过期前 30 天提醒用户重新生成
- **迁移**: 更新证书后需要在扩展中确认新指纹

### 故障排查
- **HTTPS 连接失败**: 检查证书文件路径、mkcert 是否正确安装
- **证书固定失败**: 清除 extension storage 中的旧指纹,重新信任
- **端口冲突**: 确保 8443 端口未被占用

## 参考资料

1. **OWASP Transport Layer Protection Cheat Sheet**  
   https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html

2. **Certificate Pinning Best Practices (OWASP)**  
   https://owasp.org/www-community/controls/Certificate_and_Public_Key_Pinning

3. **mkcert - Simple local HTTPS certificates**  
   https://github.com/FiloSottile/mkcert

4. **Firefox WebRequest API - getSecurityInfo**  
   https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/getSecurityInfo

5. **Bitwarden Security Architecture**  
   https://bitwarden.com/help/bitwarden-security-white-paper/  
   (参考其零知识加密模型)

6. **NIST SP 800-52 Rev. 2 - TLS Guidelines**  
   https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final

## 结论

四层安全防护架构通过**纵深防御 (Defense in Depth)** 原则,为 Keeper 提供了企业级的安全保障:

1. **传输层安全**: HTTPS 防止网络嗅探
2. **网络层隔离**: localhost 绑定限制攻击面
3. **应用层加密**: 端到端加密实现零知识架构
4. **身份验证**: 证书固定防御高级 MITM 攻击

即使某一层被攻破,其他层仍能保护用户数据。这种设计理念与军事防御、航空航天等关键领域的安全实践一致。

**最终目标**: 即使攻击者完全控制了网络和服务器,仍然无法获取用户的明文密码。
