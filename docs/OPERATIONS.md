# 万象影界 | VISTAVERSE 运行与运维手册

## 推荐运行方式

生产环境优先使用根目录 Compose：Postgres、Redis、FastAPI、用户端和管理端在同一 Compose 网络中运行。Postgres/Redis 只在内部网络可见，API 和两个 Web 端口默认只绑定宿主机回环地址；对外发布由 HTTPS 反向代理完成。

```bash
cp deploy/.env.docker.example deploy/.env.docker
# 编辑并替换所有 replace-with-* 值
docker compose --env-file deploy/.env.docker up -d
docker compose --env-file deploy/.env.docker ps
curl http://127.0.0.1:8000/api/health
```

拉取 API、用户端和管理端镜像时使用 `PRINTFILM_VERSION` 固定同一版本，例如：

```bash
PRINTFILM_VERSION=0.2.0 docker compose --env-file deploy/.env.docker pull
PRINTFILM_VERSION=0.2.0 docker compose --env-file deploy/.env.docker up -d
```

改源码时使用 `docker-compose.full.yml` 构建。只需要库和缓存、API 由宿主机运行时，使用 `deploy/docker-compose.yml`，并将 `REDIS_URL` 写成带密码的 URL。

## Windows 本机 Docker 调试基线

后端源码调试不要求先完成 API 镜像构建。推荐把 Postgres / Redis 放在 Docker，
把 `backend` 目录作为宿主机 Python 进程运行；这样可以使用当前源码和测试夹具，
同时保留与生产相同的 PostgreSQL、Redis、迁移和媒体签名约束。

```powershell
# 在仓库根目录执行；首次运行前复制并修改 deploy/.env.prod.example
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml ps

Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

宿主机 `backend/.env` 至少需要指向映射端口：

```env
DATABASE_URL=postgresql+asyncpg://printfilm:<密码>@127.0.0.1:15432/printfilm
DATABASE_URL_SYNC=postgresql+psycopg2://printfilm:<密码>@127.0.0.1:15432/printfilm
REDIS_URL=redis://:<Redis密码>@127.0.0.1:16379/0
ENVIRONMENT=production
SECRET_KEY=<至少 32 位随机字符串>
MEDIA_REQUIRE_SIGNATURE=true
```

`postgres` / `redis` 这两个服务名只在 API 也运行于 Compose 网络时有效；宿主机
API 必须使用 `127.0.0.1:15432` 和 `127.0.0.1:16379`。启动后用
`GET /api/health` 验证迁移和连接池，再用管理员令牌访问
`GET /api/health/details`。生产模式下 `/docs`、`/redoc` 和 `/openapi.json` 为
404，未签名的 `/static/generated/...` 为 403。

测试与调试：

```powershell
Set-Location backend
python -m compileall -q app tests
python -m pytest -q tests/test_kepu_shot_edit_demote.py
python -m pytest -q
```

若本地已存在 `printfilm-web:latest` 和 `printfilm-admin-web:latest`，可以把两个
静态站点也放在 Docker 中，使用 `api:host-gateway` 访问宿主机 API：

```powershell
docker run -d --name printfilm-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8080:80 printfilm-web:latest
docker run -d --name printfilm-admin-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8081:80 printfilm-admin-web:latest
Invoke-WebRequest http://127.0.0.1:8080/api/health
Invoke-WebRequest http://127.0.0.1:8081/api/health
```

这条路径只验证本地静态镜像和 API 反代；完整 API 镜像构建仍按
`docker-compose.full.yml` 单独验证。停止时执行 `docker stop` 后再 `docker rm` 这两个
容器，数据库和 Redis 卷不受影响。

测试夹具会使用独立的 `<database>_test` 数据库；确认 `DATABASE_URL` 指向本机
测试库或专用开发库，禁止把生产库连接串直接用于测试。测试完成后仅停止本次
Compose 项目即可，默认不会删除卷：

```powershell
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml --env-file deploy/.env.prod down
```

## 启动顺序与迁移

API 启动时先连接数据库，再按顺序执行 `init_db()`、模板/技能 seed 和增量 schema 迁移。增量迁移位于 `backend/app/main.py`：

- `schema_migrations` 记录已完成的版本；当前版本为 1。
- 迁移使用 PostgreSQL advisory lock，同一数据库的多个 API 实例不会并发执行 DDL。
- 现有列检查保持向后兼容，事务失败会整体回滚；不要在生产库手工删除迁移记录。
- 新增 schema 时提高 `_SCHEMA_MIGRATION_VERSION`，增加一次性、可回滚的迁移分支，并在 `backend/tests/conftest.py` 的隔离库中验证。

首次上线建议先以一个 API 实例执行迁移，确认 `/api/health` 返回成功后再启动其它 Web 服务。任务运行时是 FastAPI 进程内的 scheduler、executor、poller 和 watchdog；生产默认单 worker，重启前应观察任务是否已结算或取消。

## 备份与恢复

```bash
# 仅示例，生产请把输出写入受控备份存储
docker compose --env-file deploy/.env.docker exec -T postgres \
  sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
docker compose --env-file deploy/.env.docker exec -T postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.sql
```

同时保留 `printfilm_media` 卷。恢复后先设置 `TASK_RUNTIME_ENABLED=false` 做只读核对，再确认项目、资产、任务和计费记录一致后恢复执行。

## 运行检查

- 存活：`GET /api/health`，不包含数据库和模型细节。
- 管理诊断：管理员令牌访问 `GET /api/health/details`，查看 `db_pool`、`task_runtime`、`media_disk` 和请求错误/慢请求计数。
- 日志：按 `request_id=<X-Request-ID>`、`task_id`、`provider_task_id` 检索；外部上游失败要同时核对对应 `UsageEvent` 的结算状态。
- 媒体：确认本地 `backend/static/generated` 可写、FFmpeg/ffprobe 在 PATH，OSS 开启时确认异步队列能消费且失败会保留本地文件。
- 生产媒体：确认 `MEDIA_REQUIRE_SIGNATURE=true`；前端应使用 API 返回的 `/api/media/...?...` 短期 URL，直接访问 `/static/generated/...` 返回 403。
- 漫剧项目、资产和分集列表有服务端上限；项目列表使用 SQL 计数/封面子查询，避免把每个项目的全部分镜关系加载到内存。客户端需要更多数据时应显式分页或按项目查询。

排查任务积压时先看 scheduler 最近成功时间、连续失败次数、数据库锁等待和单用户并发槽位，再调整并发配置。增加并发不能解决迁移锁、上游限流或孤儿租约问题。

## 关闭与升级

```bash
docker compose --env-file deploy/.env.docker logs -f api
docker compose --env-file deploy/.env.docker down       # 保留卷
docker compose --env-file deploy/.env.docker up -d       # 重新启动
```

升级镜像前先备份数据库和媒体卷，固定 `PRINTFILM_VERSION`，执行健康检查和一条最小登录/任务查询流程；失败时回滚到上一镜像标签，不要删除数据卷。

