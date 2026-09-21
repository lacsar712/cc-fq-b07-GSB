from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import router
from app.database import Base, engine


# 幂等补列：create_all 不会修改已存在的表，老库升级时补齐归档列
_ARCHIVE_COLUMNS = [
    ("is_archived", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("archived_at", "TIMESTAMP WITH TIME ZONE"),
    ("archived_by", "VARCHAR(64)"),
]


def _ensure_archive_columns() -> None:
    with engine.begin() as conn:
        for name, ddl in _ARCHIVE_COLUMNS:
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {name} {ddl}"))


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
