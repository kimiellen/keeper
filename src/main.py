from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.bookmarks import router as bookmarks_router
from src.api.relations import router as relations_router
from src.api.session import SessionManager
from src.api.stats import router as stats_router
from src.api.tags import router as tags_router
from src.db.engine import create_engine, create_session_factory
from src.db.models import Base
from src.middleware.auth import AuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.session_manager = SessionManager()
    yield
    await engine.dispose()


app = FastAPI(title="Keeper API", version="1.0.0", lifespan=lifespan)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(tags_router)
app.include_router(relations_router)
app.include_router(bookmarks_router)
app.include_router(stats_router)


@app.get("/")
async def root():
    return {"message": "Keeper API", "version": "1.0.0"}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8443)
