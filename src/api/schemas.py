"""认证请求/响应 Pydantic 模型 — 对齐 docs/api.md 认证与会话管理章节。"""

from pydantic import BaseModel, Field


class KdfParams(BaseModel):
    algorithm: str = Field(default="Argon2id")
    memory: int = Field(default=65536)
    iterations: int = Field(default=3)
    parallelism: int = Field(default=1)
    salt: str


class InitializeRequest(BaseModel):
    email: str = Field(min_length=1)
    masterPasswordHash: str = Field(min_length=1)
    encryptedUserKey: str = Field(min_length=1)
    kdfParams: KdfParams


class InitializeResponse(BaseModel):
    message: str = "初始化成功"


class UnlockRequest(BaseModel):
    masterPasswordHash: str = Field(min_length=1)


class UnlockResponse(BaseModel):
    message: str = "解锁成功"
    encryptedUserKey: str
    kdfParams: KdfParams


class StatusResponseUnlocked(BaseModel):
    locked: bool = False
    sessionExpiresAt: str


class StatusResponseLocked(BaseModel):
    locked: bool = True
