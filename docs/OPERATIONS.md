# 万象影界 | VISTAVERSE 运行与运维手册

## 推荐运行方式

生产环境优先使用根目录 Compose：Postgres、Redis、FastAPI、用户端和管理端在同一 Compose 网络中运行。Postgres/Redis 只在内部网络可见，API 和两个 Web 端口默认只绑定宿主机回环地址；对外发布由 HTTPS 反向代理完成。

```bash
cp deploy/.env.docker.example deploy/.env.docker
# 编辑并替换所有 replace-with-* 值
python deploy/scripts/check_release.py build-metadata --output deploy/build.env
# 按 deploy/README.md 的 immutable release 流程从已拉取镜像生成 release.lock.yml
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml config --quiet
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml up -d --no-build
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml ps
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
```

拉取 API、用户端和管理端镜像时使用 `PRINTFILM_VERSION` 固定同一版本，例如：

```bash
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml pull
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml up -d --no-build
```

改源码时先运行 `check_release.py build-metadata`，再使用 `docker-compose.full.yml` 构建。只需要库和缓存、API 由宿主机运行时，使用 `deploy/docker-compose.yml`，并将 `REDIS_URL` 写成带密码的 URL。

## Ubuntu 服务器部署（IP 测试环境）

当前服务器部署目录为 `/opt/vistaverse/current`，发布版本保存在
`/opt/vistaverse/releases/<UTC 时间戳>`；Compose 项目名固定为 `vistaverse`，使用
`docker-compose.full.yml` 和服务器专用 `deploy/.env.docker`。PostgreSQL、Redis、API
和两个静态站点均由 Docker 管理，数据卷为 `vistaverse_printfilm_pgdata`、
`vistaverse_printfilm_redisdata` 和 `vistaverse_printfilm_media`。

服务器只有 IP、尚未配置域名和证书，因此当前配置是隔离的 HTTP 测试环境：
`ENVIRONMENT=development`、`ARK_MOCK=true`、`BILLING_ENABLED=false`，不可作为公网
生产配置。正式上线前必须换成真实域名和 HTTPS，并填入真实上游密钥后改为
`ENVIRONMENT=production`。

```bash
cd /opt/vistaverse/current
sudo docker compose -p vistaverse --env-file deploy/.env.docker \
  -f docker-compose.full.yml ps -a
curl -fsS http://127.0.0.1:8000/api/health
sudo journalctl -u vistaverse.service -n 100 --no-pager
sudo docker compose -p vistaverse --env-file deploy/.env.docker \
  -f docker-compose.full.yml logs --tail=200 api
```

`vistaverse.service` 已启用，负责开机执行 `docker compose up -d`；各容器也使用
`restart: unless-stopped`。主站和管理端均可通过宿主 Nginx 的 `80` 端口访问：用户端为
`/`，管理端为 `/admin/`。独立管理端端口 `8081` 仍转发到回环端口 `18081`，API 只绑定
回环 `8000`。UFW 允许 `22/tcp`、`80/tcp` 和 `8081/tcp`；若云厂商安全组未放行
`8081`，使用 `http://<服务器 IP>/admin/`，或通过 SSH 隧道访问：
`ssh -L 8081:127.0.0.1:18081 ubuntu@<服务器 IP>`。

升级前先备份数据库和媒体卷，再把 `current` 切换到新发布目录并重启服务；回滚时切回
上一版本目录，保留数据卷，不执行 `docker compose down -v`。服务器已保留初始
PostgreSQL 压缩备份在 `/opt/vistaverse/backups/`。

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
TRUSTED_PROXY_IPS=<反向代理网段；直连 API 留空>
FFMPEG_TIMEOUT_SEC=1800
```

`postgres` / `redis` 这两个服务名只在 API 也运行于 Compose 网络时有效；宿主机
API 必须使用 `127.0.0.1:15432` 和 `127.0.0.1:16379`。启动后用
`GET /api/ready` 主动验证数据库、Redis 和任务运行时，再用管理员令牌访问
`GET /api/health/details`。生产模式下 `/docs`、`/redoc` 和 `/openapi.json` 为
404，未签名的 `/static/generated/...` 为 403。

复制 `deploy/.env.docker.example` 后必须替换 `your-domain.example` 占位域名；生产 API 会拒绝全为
localhost 的 CORS 配置。生产计费应保持 `BILLING_ENABLED=true`，关闭计费只适用于隔离演示环境。

测试与调试：

```powershell
Set-Location backend
python -m compileall -q app tests
python -m pytest -q tests/test_kepu_shot_edit_demote.py
python -m pytest -q
```

若本地已存在 与本次提交对应的 `printfilm-web:<release-tag>` 和 `printfilm-admin-web:<release-tag>`，可以把两个
静态站点也放在 Docker 中，使用 `api:host-gateway` 访问宿主机 API：

```powershell
docker run -d --name printfilm-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8080:80 printfilm-web:<release-tag>
docker run -d --name printfilm-admin-web-local `
  --add-host api:host-gateway -p 127.0.0.1:8081:80 printfilm-admin-web:<release-tag>
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

- `schema_migrations` 记录已完成的版本；当前版本为 2。
- 迁移使用 PostgreSQL advisory lock，同一数据库的多个 API 实例不会并发执行 DDL。
- 现有列检查保持向后兼容，事务失败会整体回滚；不要在生产库手工删除迁移记录。
- 新增 schema 时提高 `_SCHEMA_MIGRATION_VERSION`，增加一次性、可回滚的迁移分支，并在 `backend/tests/conftest.py` 的隔离库中验证。

首次上线建议先以一个 API 实例执行迁移，确认 `/api/ready` 返回成功后再启动其它 Web 服务。任务运行时是 FastAPI 进程内的 scheduler、executor、poller 和 watchdog；生产默认单 worker，重启前应观察任务是否已结算或取消。

## 备份与恢复

数据库备份必须包含 schema、业务表和迁移记录，并与媒体卷的同一备份批次关联。备份应加密、异机保存，限制凭据和读取权限，设定保留策略。仅存在 `.sql`/归档文件不代表可恢复。

恢复验证必须使用独立 Compose 项目、独立数据库/媒体卷和未对公网发布的端口；禁止把恢复命令直接指向生产 PostgreSQL。验证实例设置 `TASK_RUNTIME_ENABLED=false`、关闭支付/邮件/外部模型及 OSS 队列，再导入备份；核对 schema migration v2、关键业务行数、外键、媒体清单/校验和、认证后只读查询。记录备份时间、校验和、恢复耗时、RPO/RTO、失败项和审核人。演练通过后保留报告，按授权单独清理隔离卷。

完整监控及隔离恢复验收流程见 [PRODUCTION_VERIFICATION.md](PRODUCTION_VERIFICATION.md)。该流程与脚本是待执行的操作材料，不能作为已经完成线上监控/恢复演练的证据。

## 运行检查

- 存活：`GET /api/health`，不包含数据库和模型细节。
- 就绪：`GET /api/ready`；主动执行有时限的数据库/Redis 检查，任务运行时未就绪时返回 503。Compose/Docker HEALTHCHECK 使用此接口；存活 200 不能替代依赖检查。
- 管理诊断：管理员令牌访问 `GET /api/health/details`，查看 `db_pool`、`task_runtime`、`media_disk` 和请求错误/慢请求计数。
- 日志：按 `request_id=<X-Request-ID>`、`task_id`、`provider_task_id` 检索；外部上游失败要同时核对对应 `UsageEvent` 的结算状态。
- 媒体：确认本地 `backend/static/generated` 可写、FFmpeg/ffprobe 在 PATH，OSS 开启时确认异步队列能消费且失败会保留本地文件。
- 生产媒体：确认 `MEDIA_REQUIRE_SIGNATURE=true`；前端应使用 API 返回的 `/api/media/...?...` 短期 URL，直接访问 `/static/generated/...` 返回 403。
- 漫剧项目、资产和分集列表有服务端上限；项目列表使用 SQL 计数/封面子查询，避免把每个项目的全部分镜关系加载到内存。客户端需要更多数据时应显式分页或按项目查询。

排查任务积压时先看 scheduler 最近成功时间、连续失败次数、数据库锁等待和单用户并发槽位，再调整并发配置。增加并发不能解决迁移锁、上游限流或孤儿租约问题。

## 关闭与升级

```bash
docker compose --env-file deploy/.env.docker logs -f api
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml down       # 保留卷
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml up -d --no-build       # 重新启动
```

升级镜像前先备份数据库和媒体卷，固定 `PRINTFILM_VERSION`，执行健康检查和一条最小登录/任务查询流程；失败时回滚到上一镜像标签，不要删除数据卷。


## 镜像发布与依赖持久性

两套根 Compose 均要求显式填写 `PRINTFILM_VERSION`，不再默认 `latest` 或旧版本。生产使用 `git-<完整提交SHA>` 等唯一 tag，API/Web/Admin 必须来自同一提交；注册表必须开启 tag 不可覆盖策略。tag 本身并非 Docker 强制的不可变内容地址，发布证据还必须记录 `docker image inspect` 的 RepoDigests/Image ID，并在 registry 侧验证 tag 未被覆盖。每次本地构建也使用新 tag，禁止复用生产 tag。基础镜像仍固定版本标签，严格供应链部署应额外解析并锁定经过审核的 digest。

Redis 改为 `noeviction`，避免队列在缓存压力下静默丢失；达到 512 MiB 上限时写请求会明确失败，因此必须监控 `used_memory`、`evicted_keys`、`rejected_connections`、AOF 写入状态及后台队列积压。Redis AOF 不替代 PostgreSQL/媒体备份，主机磁盘丢失仍会损失本机 AOF。

上述配置仅在发布该版本后生效；本地检查不能证明服务器已完成镜像切换、监控接入或恢复演练。
