# VISTAVERSE 操作手册（技能参考）

## Compose 校验与启动

```powershell
docker context show
docker compose --env-file deploy/.env.docker -f docker-compose.yml config --quiet
docker compose --env-file deploy/.env.docker -f docker-compose.full.yml config --quiet
docker compose --env-file deploy/.env.docker -f docker-compose.full.yml up -d --build
docker compose --env-file deploy/.env.docker -f docker-compose.full.yml ps -a
```

`deploy/.env.docker` 是本地忽略文件，先复制 `deploy/.env.docker.example` 并填写随机密码；不要把解析后的
Compose 配置或日志直接粘贴到公开报告。

## 中间件 + 宿主机 API

```powershell
docker compose -p printfilm-local-middleware -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d
docker compose -p printfilm-local-middleware -f deploy/docker-compose.yml ps -a
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

生产环境必须设置至少 32 位随机 `SECRET_KEY`、真实 `CORS_ORIGINS`、带密码的 `REDIS_URL`，并启用
`MEDIA_REQUIRE_SIGNATURE=true`；生产 API 的 `/docs`、`/redoc` 与 `/openapi.json` 应保持关闭。

## 日志、健康和停止

```powershell
docker compose -p printfilm-local-middleware -f deploy/docker-compose.yml --env-file deploy/.env.prod logs --tail=200
docker compose -p printfilm-local-middleware -f deploy/docker-compose.yml --env-file deploy/.env.prod down
```

`/api/health` 是存活检查，不证明数据库、Redis 或上游模型可用；管理员登录后再查 `/api/health/details`。

## 服务器边界

- 仅反向代理暴露 Web/API；PostgreSQL 与 Redis 绑定回环或私有网络，公网只开放 HTTPS 入口。
- 保留 `printfilm_pgdata` 与 `printfilm_media`；Redis 只保存队列/进度，不能替代数据库备份。
- 单 worker 是当前进程内任务平台的设计约束；扩展副本前先拆出调度/执行器并验证迁移锁、租约和幂等性。
- 低配可用起点：2 vCPU、4 GB RAM、40 GB SSD；建议生产 4 vCPU、8 GB RAM、100 GB SSD，媒体生成量增长时单独扩容媒体盘。
