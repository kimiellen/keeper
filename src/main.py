import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.bookmarks import router as bookmarks_router
from src.api.database import router as database_router
from src.api.relations import router as relations_router
from src.api.session import SessionManager
from src.api.stats import router as stats_router
from src.api.tags import router as tags_router
from src.api.transfer import router as transfer_router
from src.db.config import DatabaseConfig
from src.db.engine import DatabaseManager
from src.middleware.auth import AuthMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.security import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_config = DatabaseConfig()
    db_manager = DatabaseManager()

    # 优先使用上次记录的数据库；没有则等待前端插件通过 /api/db/create 新建
    current = db_config.get_current()
    if current:
        await db_manager.initialize(current)

    app.state.db_config = db_config
    app.state.db_manager = db_manager
    app.state.engine = db_manager.engine
    app.state.session_factory = db_manager.session_factory
    app.state.session_manager = SessionManager()
    yield
    await db_manager.dispose()


app = FastAPI(title="Keeper API", version="1.0.0", lifespan=lifespan)

_raw_origins = os.environ.get("KEEPER_CORS_ORIGINS", "").split(",")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins if o.strip()]

CORS_ORIGIN_REGEX = os.environ.get(
    "KEEPER_CORS_ORIGIN_REGEX", r"^(moz-extension|chrome-extension)://.*$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=86400,
)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(database_router)
app.include_router(tags_router)
app.include_router(relations_router)
app.include_router(bookmarks_router)
app.include_router(stats_router)
app.include_router(transfer_router)


@app.get("/")
async def root():
    return {"message": "Keeper API", "version": "1.0.0"}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    ssl_keyfile = os.environ.get("KEEPER_SSL_KEYFILE", "certs/localhost+2-key.pem")
    ssl_certfile = os.environ.get("KEEPER_SSL_CERTFILE", "certs/localhost+2.pem")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8443,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
