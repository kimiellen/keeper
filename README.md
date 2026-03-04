# Keeper

密码管理器后端 API

## 技术栈

- FastAPI (Python)
- SQLite
- JWT 认证
- uv (工程化管理)

## 开发

```bash
# 安装 uv (如果未安装)
# curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖并创建虚拟环境
uv sync

# 启动开发服务器
uv run uvicorn src.main:app --reload

# 或者
uv run fastapi dev src/main.py
```

## API 文档

启动后访问 http://localhost:8000/docs
