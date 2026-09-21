# FASTQ 质控流水线台（FASTQ QC Pipeline Console）

从零实现的全栈演示：上传/选择小型 FASTQ → **Actor 队列流水线**质控 → 查看阶段状态与指标。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL |
| 流水线 | `ParseActor` → `QualityHistActor` → `NContentActor` → `ReportActor`（asyncio.Queue） |
| 前端 | Vue 3 · Vite · Quasar · 中文 UI · nginx `/api` 反代 |
| 基建 | docker compose（db / backend / seed / frontend） |

## 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3184 |
| Backend API | http://localhost:8184 |
| PostgreSQL | localhost:54384 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| `bioops` | `fastq123456` | 可提交质控作业、归档成功作业 |
| `auditor` | `audit123456` | 只读结果，不可提交 / 不可归档 |

## 一键启动

```bash
cd projects/09-fastq-qc-pipeline
docker compose up --build
```

镜像源：Postgres/Node/Nginx 使用 `docker.m.daocloud.io`；npm 使用 `registry.npmmirror.com`；pip 使用清华源。

启动后 seed 会写入：

- `demo-good-r1`：合格样例（可算出 `mean_quality` / `n_rate`）
- `demo-broken-malformed`：损坏样例（`ParseActor` 失败，后续阶段 skipped）

## Verification（验收）

1. 打开 http://localhost:3184 ，用 `bioops` / `fastq123456` 登录。
2. **样例库** 看到 2 条样例 → 选合格样例 **提交质控作业**。
3. 作业详情页看到四个 Actor 阶段均为成功，指标卡出现 `reads` / `mean_quality` / `n_rate`。
4. 再跑损坏样例：`ParseActor` = failed，其余 = skipped。
5. 退出，用 `auditor` / `audit123456` 登录：可看历史与详情，提交作业接口返回 403 / 前端无提交入口。
6. 健康检查：`curl http://localhost:8184/api/health`

## 归档层

成功作业可收进归档层，让默认历史更干净。约定：

1. **只有成功态允许归档**，且仅由运维（`bioops`）执行；失败 / 运行中作业调用归档接口返回 400，审计员返回 403。
2. **默认历史隐藏已归档条目**；历史页打开「含归档」开关（等价于 `include_archived=true`）仍可看见并进入详情。
3. **审计员只读**：可见默认 / 含归档列表与详情，但不能归档。
4. **阶段记录与指标不做物理删除**——归档只是 `is_archived` 标记，`/jobs/{id}` 与 `/jobs/{id}/stages` 原样可取。
5. 对外映射维持：作业 id、样例关联、详情 URL 均不变。

归档自测：作业成功后在历史页点「归档」→ 默认列表不再有它 → 打开「含归档」仍能看到并点进详情（阶段与指标都在）。

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
- `GET  /api/jobs`（默认仅未归档；`?include_archived=true` 含已归档）
- `GET  /api/jobs/{id}`（归档作业详情照常可查）
- `GET  /api/jobs/{id}/stages`
- `POST /api/jobs/{id}/archive`（仅 `bioops` + `status=success`）

## 本地单测（可选）

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

覆盖：畸形 FASTQ 在 `ParseActor` 失败；正常样例产出 `mean_quality`；归档权限（仅成功 / 仅运维 / 404 / 重复归档 400）与可见性（默认隐藏、开关可见、详情与阶段指标保留）。

## 目录结构

```
09-fastq-qc-pipeline/
  PRD.md
  README.md
  docker-compose.yml
  backend/
    Dockerfile
    seed.py
    data/{good,broken}.fastq
    app/
      main.py api.py auth.py models.py schemas.py
      pipeline/{actors,runner}.py
    tests/{conftest,test_actors,test_archive}.py
  frontend/
    Dockerfile nginx.conf
    src/pages/{Login,Samples,JobSubmit,JobDetail,JobHistory}Page.vue
```
