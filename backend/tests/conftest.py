"""Pytest 配置：在导入任何 app 模块之前把数据库切到临时 SQLite 文件。"""

import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "fastq_qc_test.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_jobs(client):
    """每个用例前清空作业相关表（依赖 client 以确保表已建好；样例表不在测试中使用）。"""
    from app.models import Job, JobStage

    db = SessionLocal()
    try:
        db.query(JobStage).delete()
        db.query(Job).delete()
        db.commit()
    finally:
        db.close()
    yield


def login(client, username: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
