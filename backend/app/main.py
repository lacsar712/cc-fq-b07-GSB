from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import router
from app.database import Base, engine


# 旧库（jobs 表已存在但缺少归档列）的轻量幂等迁移；create_all 只建新表不补列
_ARCHIVE_COLUMNS = {
    "is_archived": "BOOLEAN NOT NULL DEFAULT FALSE",
    "archived_at": "TIMESTAMP WITH TIME ZONE",
    "archived_by": "VARCHAR(64)",
}


def _ensure_archive_columns() -> None:
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("jobs")}
    with engine.begin() as conn:
        for name, ddl in _ARCHIVE_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))
        # is_archived 索引（新旧库一致），IF NOT EXISTS 在 PG/SQLite 均受支持
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_is_archived ON jobs (is_archived)")
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_archive_columns()
    yield


app = FastAPI(title="FASTQ QC Pipeline Console", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
