"""归档层 API 自测：默认隐藏、含归档可见、仅成功态可归档、审计员只读、不物理删除。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Job, JobStage
from app.pipeline.actors import ACTOR_CHAIN


# 用内存 SQLite 替换 Postgres，全程不触碰真实库
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)  # 不进入 with：不触发 lifespan（避免连真实 Postgres）

_PASSWORDS = {"bioops": "fastq123456", "auditor": "audit123456"}
GOOD_METRICS = {"reads": 2, "mean_quality": 36.5, "n_rate": 0.0}


def _auth(role: str) -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"username": role, "password": _PASSWORDS[role]},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_job(status: str, metrics=None, created_by: str = "bioops") -> int:
    db = TestSession()
    job = Job(
        sample_name="自定义输入",
        status=status,
        created_by=created_by,
        fastq_snapshot="@A\nACGT\n+\nIIII\n",
        metrics=metrics,
        finished_at=datetime.now(timezone.utc) if status in ("success", "failed") else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    for order, cls in enumerate(ACTOR_CHAIN):
        db.add(
            JobStage(
                job_id=job.id,
                actor_name=cls.name,
                stage_order=order,
                status="success" if status == "success" else "pending",
            )
        )
    db.commit()
    jid = job.id
    db.close()
    return jid


def test_archived_hidden_by_default_visible_with_flag_and_detail_accessible():
    jid = _make_job("success", metrics=GOOD_METRICS)

    # 归档前默认列表可见
    rows = client.get("/api/jobs", headers=_auth("auditor")).json()
    assert any(j["id"] == jid for j in rows)

    # 运维执行归档
    resp = client.post(f"/api/jobs/{jid}/archive", headers=_auth("bioops"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_archived"] is True
    assert body["archived_by"] == "bioops"
    assert body["archived_at"] is not None

    # 自测核心：收入归档后默认列表没有它
    rows = client.get("/api/jobs", headers=_auth("auditor")).json()
    assert all(j["id"] != jid for j in rows)

    # 打开含归档开关仍可看见
    rows = client.get(
        "/api/jobs", params={"include_archived": "true"}, headers=_auth("auditor")
    ).json()
    hit = next(j for j in rows if j["id"] == jid)
    assert hit["is_archived"] is True

    # 仍可进入详情
    detail = client.get(f"/api/jobs/{jid}", headers=_auth("auditor"))
    assert detail.status_code == 200
    assert detail.json()["is_archived"] is True

    # 阶段记录与指标不得物理删除
    stages = client.get(f"/api/jobs/{jid}/stages", headers=_auth("auditor")).json()
    assert len(stages) == len(ACTOR_CHAIN)
    assert detail.json()["metrics"] == GOOD_METRICS


def test_only_success_job_can_be_archived():
    jid = _make_job("failed")
    resp = client.post(f"/api/jobs/{jid}/archive", headers=_auth("bioops"))
    assert resp.status_code == 400

    db = TestSession()
    job = db.query(Job).filter(Job.id == jid).first()
    assert job.is_archived is False
    assert job.archived_at is None
    db.close()


def test_auditor_is_read_only():
    jid = _make_job("success", metrics=GOOD_METRICS)
    resp = client.post(f"/api/jobs/{jid}/archive", headers=_auth("auditor"))
    assert resp.status_code == 403

    # 作业未被归档
    rows = client.get("/api/jobs", headers=_auth("bioops")).json()
    assert next(j for j in rows if j["id"] == jid)["is_archived"] is False


def test_archive_unknown_job_404():
    resp = client.post("/api/jobs/999999/archive", headers=_auth("bioops"))
    assert resp.status_code == 404


def test_archive_requires_login():
    jid = _make_job("success", metrics=GOOD_METRICS)
    assert client.post(f"/api/jobs/{jid}/archive").status_code == 401
