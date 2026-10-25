# 万象影界 | VISTAVERSE 部署（Docker 只跑库与缓存）

> 开源仓库以根目录 [README.md](../README.md) 的 Docker 全栈为准。  
> 现网机器发布手册 `docs/DEPLOY.md`、发版记录 `docs/releases/` 仅本机保留，不上库。  
> 本文仅描述 Postgres/Redis compose 与本机跑 API 的补充说明。技术服务名仍使用
> `printfilm`；**不要**用 OSS 上传前端 dist 代替站点发布。

## 分工

| 组件 | 运行方式 |
|------|----------|
| PostgreSQL | Docker |
| Redis | Docker |
| FastAPI / 进程内任务平台 | 同一个宿主机 Python 进程 |
| 前端 / 管理后台 | 宿主机 `npm run build` + nginx 静态托管 |

## 1. 启动中间件（独立目录，不复用其它项目的库）

```bash
cp deploy/.env.prod.example deploy/.env.prod   # 改密码；默认端口 15432 / 16379
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d
docker compose -f deploy/docker-compose.yml ps
```

Windows / Docker Desktop 也可显式固定 Compose 项目名，避免与其他工作区的
`ai-movie-pg` / `ai-movie-redis` 混用：

```powershell
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml ps
```

本机调试时，PostgreSQL 和 Redis 的宿主端口分别是 `127.0.0.1:15432` 与
`127.0.0.1:16379`；API 进程使用容器端口映射外的宿主地址连接它们。不要把
`DATABASE_URL` 写成 Compose 服务名 `postgres` / `redis`，那只适用于 API 也在
同一个 Compose 网络中的全栈模式。

容器名：`ai-movie-pg`、`ai-movie-redis`。与 kepu（5432/6379）隔离。

Postgres / Redis 端口只绑定 `127.0.0.1`，不会直接暴露到公网；远程维护请使用 SSH 隧道。Redis 必须设置 `REDIS_PASSWORD`，应用连接串写成 `redis://:<密码>@127.0.0.1:16379/0`。常规发布默认**不**执行 `docker compose`（见 `SETUP_INFRA=1`）。

## 2. 配置应用

将 `deploy/.env.prod` 中的 `DATABASE_URL` / `REDIS_URL` / `ARK_*` 等写入 `backend/.env`（密码与 compose 一致）。

正式环境示例：

```env
DATABASE_URL=postgresql+asyncpg://printfilm:<密码>@127.0.0.1:15432/printfilm
DATABASE_URL_SYNC=postgresql+psycopg2://printfilm:<密码>@127.0.0.1:15432/printfilm
REDIS_URL=redis://:<Redis密码>@127.0.0.1:16379/0
ENVIRONMENT=production
SECRET_KEY=<至少 32 位随机字符串>
TASK_RUNTIME_MAX_CONCURRENCY=4
TASK_USER_MAX_CONCURRENCY=4
```

需本机已安装：Python 3.12、FFmpeg（PATH）、Node.js。

### 本机源码 API 调试（Docker 中间件 + 宿主机 Python）

这是排查后端代码时的推荐方式：数据库和缓存留在 Docker，源码由宿主机
`uvicorn` 直接加载，修改 Python 文件后可立即重启进程。将下面的连接串和
`deploy/.env.prod` 中的实际密码保持一致，保存为 `backend/.env`（该文件已被
忽略，不要提交）：

```env
DATABASE_URL=postgresql+asyncpg://printfilm:<密码>@127.0.0.1:15432/printfilm
DATABASE_URL_SYNC=postgresql+psycopg2://printfilm:<密码>@127.0.0.1:15432/printfilm
REDIS_URL=redis://:<Redis密码>@127.0.0.1:16379/0
ENVIRONMENT=production
SECRET_KEY=<至少 32 位随机字符串>
MEDIA_REQUIRE_SIGNATURE=true
MEDIA_SIGNED_URL_TTL_SEC=900
ARK_MOCK=true
TASK_RUNTIME_ENABLED=true
```

在 PowerShell 中启动：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

启动后先检查 `http://127.0.0.1:8000/api/health`。`ENVIRONMENT=production`
时 `/docs`、`/redoc`、`/openapi.json` 应返回 404；本地生成媒体必须通过 API
返回的短期签名 URL 读取，直接访问 `/static/generated/...` 应返回 403。
需要只看界面而不调用上游模型时保持 `ARK_MOCK=true`；真实生图/生视频前再填
入 `ARK_API_KEY` / `OPENAI_API_KEY` 并重启 API。

停止宿主机 API 使用 `Ctrl+C`；停止 Docker 中间件但保留数据卷：

```powershell
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml --env-file deploy/.env.prod down
```

如果已经构建出本地用户端和管理端镜像，也可以让两个静态站点继续运行在
Docker 中，并把 `/api` 反代到宿主机 API（`api:host-gateway`）：

```powershell
docker run -d --name printfilm-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8080:80 printfilm-web:latest
docker run -d --name printfilm-admin-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8081:80 printfilm-admin-web:latest

Invoke-WebRequest http://127.0.0.1:8080/api/health
Invoke-WebRequest http://127.0.0.1:8081/api/health
docker stop printfilm-web-local printfilm-admin-web-local
docker rm printfilm-web-local printfilm-admin-web-local
```

这两个容器只使用本地静态镜像；完整 API 镜像仍应通过根目录
`docker-compose.full.yml` 构建或从发布仓库拉取。若外部基础镜像或 PyPI 下载受限，
保留“Docker 中间件 + 宿主机源码 API”的调试方式即可，不要把静态站点容器通过
`api:8000` 指向不存在的 Compose 服务。

**中文字幕字体（必装）**：科普成片用 FFmpeg `drawtext` 烧录叠字/口播字幕。Ubuntu 示例：

```bash
sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei fontconfig
# 可选：写入 backend/.env
# FRAMECUT_FONT=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
```

缺字体时字幕会显示为「方框」（□），需装字体后**重新合成**该项目成片。

## 3. 启动 API 与任务平台

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux:  source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

调度器、执行器、轮询器与看门狗随 API 启动，无需单独的 Celery worker。OSS 上传在后台任务平台执行。API 启动时会在 PostgreSQL advisory lock 下执行版本化 schema 迁移；生产多副本前必须先迁移任务执行器。

## 4. 前端

```bash
cd frontend
npm install
npm run dev          # 开发
# npm run build && npx serve dist   # 简单静态托管
```

## 运维

```bash
# 看中间件日志
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod logs -f

# 停中间件（不删数据）
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod down

# 停并删卷（清库/清 Redis；仅测试环境）
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod down -v
```

公共存活检查为 `GET /api/health`；数据库池、任务运行时和请求统计只在管理员身份访问 `GET /api/health/details` 时返回。健康检查、备份和升级流程详见 [../docs/OPERATIONS.md](../docs/OPERATIONS.md)，密钥与暴露面检查详见 [../docs/SECURITY.md](../docs/SECURITY.md)。

任务并发：通过 `backend/.env` 中的 `TASK_RUNTIME_MAX_CONCURRENCY`、`TASK_USER_MAX_CONCURRENCY` 调整统一任务平台并发。

测试环境由 Jenkins 轮询 **GitHub 仓库 `kevinsuperme/VISTAVERSE` 的 `dev` 分支**自动发布；日常测试发版提交并推送代码即可，不需要手动上传补丁或更新服务器容器。本仓库的 `origin` 指向 GitCC，单独 `git push origin dev` 不会触发测试发版；提交后还需 `git push github dev`，再核对 Jenkins 构建版本与运行中的镜像标签一致。

本地 API 联调连接共享测试数据库时，设置 `TASK_RUNTIME_ENABLED=false`，只保留测试服务器执行调度、轮询和孤儿恢复。已由服务器初始化的共享数据库还可设 `DATABASE_BOOTSTRAP_ENABLED=false`，本机只读取模型缓存，不再重复建表、补列、seed 或提升管理员。本地仍能创建和查询任务，执行与产物存储由测试服务器负责；本地页面应能访问服务器返回的媒体地址。独立本地数据库或实际执行节点保持两个开关为 `true`（默认）。不要让多个调试实例同时恢复同一队列。

任务中心区分「待调度」（已到期）、「待激活」（尚无调度时间，可能等前置镜或额度）和「延时等待」。排查积压时一起查看调度最近成功时间、连续失败次数、数据库锁等待；增加并发无法解决调度停滞或锁等待。

## OSS（成片 / 分镜 / 前端）

在 `backend/.env` 开启：

```env
OSS_ENABLED=true
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_BUCKET=your-bucket
OSS_FOLDER=kepu
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
```

- 分镜图/视频/配音/成片：本地落盘供 FFmpeg，上传后 DB 存 OSS 公网 URL（前端预览走 OSS）
- 对象前缀：`kepu/generated/p{id}/...`
- 前端构建产物上传：

```bash
cd frontend && npm run build
cd ../backend && .venv/bin/python ../deploy/scripts/upload_oss_web.py
# → https://{bucket}.oss-cn-beijing.aliyuncs.com/kepu/index.html
```
