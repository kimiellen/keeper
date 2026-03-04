# Keeper

密码管理器后端 API

## 技术栈

- FastAPI (Python)
- SQLite
- JWT 认证

## 开发

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn src.main:app --reload

# 或者
fastapi dev src/main.py
```

## API 文档

启动后访问 http://localhost:8000/docs
