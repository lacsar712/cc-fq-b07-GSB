"""归档层接口测试：成功态可归档、运维专属、默认隐藏、开关可见、数据不删。"""

from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Job, JobStage


def login(client, username: str, password: str) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_job(status: str = "success", archived: bool = False) -> int:
    db = SessionLocal()
    try:
        job = Job(
            sample_id=None,
            sample_name="自定义输入",
            status=status,
            created_by="bioops",
            metrics={"reads": 2, "mean_quality": 39.5, "n_rate": 0.0} if status == "success" else None,
            error_message=None if status == "success" else "流水线失败",
            fastq_snapshot="@A\nACGT\n+\nIIII\n",
            finished_at=datetime.now(timezone.utc),
            is_archived=archived,
        )
        db.add(job)
        db.flush()
        db.add(
            JobStage(
                job_id=job.id,
                actor_name="ParseActor",
                stage_order=0,
                status="success",
                message="完成",
            )
        )
        db.commit()
        return job.id
    finally:
        db.close()


def test_only_success_job_can_be_archived(client):
    headers = login(client, "bioops", "fastq123456")
    failed_id = _make_job("failed")
    success_id = _make_job("success")

    resp = client.post(f"/api/jobs/{failed_id}/archive", headers=headers)
    assert resp.status_code == 400

    resp = client.post(f"/api/jobs/{success_id}/archive", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_archived"] is True
    assert body["archived_by"] == "bioops"
    assert body["archived_at"] is not None


def test_duplicate_archive_rejected(client):
    headers = login(client, "bioops", "fastq123456")
    job_id = _make_job("success")
    assert client.post(f"/api/jobs/{job_id}/archive", headers=headers).status_code == 200
    resp = client.post(f"/api/jobs/{job_id}/archive", headers=headers)
    assert resp.status_code == 400


def test_auditor_cannot_archive(client):
    job_id = _make_job("success")
    headers = login(client, "auditor", "audit123456")
    resp = client.post(f"/api/jobs/{job_id}/archive", headers=headers)
    assert resp.status_code == 403


def test_anonymous_cannot_archive(client):
    job_id = _make_job("success")
    resp = client.post(f"/api/jobs/{job_id}/archive")
    assert resp.status_code == 401


def test_default_list_hides_archived_include_flag_shows(client):
    headers = login(client, "bioops", "fastq123456")
    kept_id = _make_job("success")
    archived_id = _make_job("success")
    client.post(f"/api/jobs/{archived_id}/archive", headers=headers)

    default_ids = {j["id"] for j in client.get("/api/jobs", headers=headers).json()}
    assert kept_id in default_ids
    assert archived_id not in default_ids

    all_ids = {
        j["id"]
        for j in client.get("/api/jobs?include_archived=true", headers=headers).json()
    }
    assert kept_id in all_ids
    assert archived_id in all_ids

    # include_archived=false 显式传参也应隐藏
    hidden_ids = {
        j["id"]
        for j in client.get("/api/jobs?include_archived=false", headers=headers).json()
    }
    assert archived_id not in hidden_ids


def test_auditor_readonly_but_sees_archive_switch_results(client):
    # 运维归档一条
    ops = login(client, "bioops", "fastq123456")
    archived_id = _make_job("success")
    client.post(f"/api/jobs/{archived_id}/archive", headers=ops)

    # 审计员：默认看不到，开关后能看到，且能进详情
    auditor = login(client, "auditor", "audit123456")
    default_ids = {j["id"] for j in client.get("/api/jobs", headers=auditor).json()}
    assert archived_id not in default_ids

    all_ids = {
        j["id"] for j in client.get("/api/jobs?include_archived=true", headers=auditor).json()
    }
    assert archived_id in all_ids

    detail = client.get(f"/api/jobs/{archived_id}", headers=auditor).json()
    assert detail["id"] == archived_id
    assert detail["is_archived"] is True
    assert detail["metrics"]["reads"] == 2


def test_archived_job_detail_and_stages_not_deleted(client):
    headers = login(client, "bioops", "fastq123456")
    job_id = _make_job("success")
    client.post(f"/api/jobs/{job_id}/archive", headers=headers)

    detail = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["metrics"]["mean_quality"] == 39.5

    stages = client.get(f"/api/jobs/{job_id}/stages", headers=headers)
    assert stages.status_code == 200
    stage_names = [s["actor_name"] for s in stages.json()]
    assert "ParseActor" in stage_names


def test_archive_nonexistent_job_404(client):
    headers = login(client, "bioops", "fastq123456")
    resp = client.post("/api/jobs/999999/archive", headers=headers)
    assert resp.status_code == 404
