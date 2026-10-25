# 万象影界 | VISTAVERSE 安全基线与威胁边界

本文描述当前代码可验证的安全约束，以及部署者必须承担的配置责任。它与 `docs/STANDARDS.md` 一起作为发布前检查清单。

## 已落实的基线

- `ENVIRONMENT=production`、`prod` 或 `staging` 启动时，`SECRET_KEY` 必须至少 32 个字符，且不能使用示例值；数据库连接串也不能使用仓库示例密码。
- 开发环境不配置密钥时只生成一次性随机密钥，重启会使本地会话失效。生产环境不会自动生成密钥。
- 生产环境默认关闭 FastAPI `/docs`、`/redoc` 和 `/openapi.json`。需要开放接口文档时，应在受控的内网或已认证反向代理后单独开放。
- 公共 `/api/health` 只返回存活状态；数据库连接池、任务运行时、媒体磁盘、模型名和请求统计位于需要管理员身份的 `/api/health/details`。
- 每个 HTTP 响应带 `X-Request-ID`。客户端提供的值仅在可打印 ASCII、长度不超过 64 时复用，否则生成随机值；该值用于日志关联，不是鉴权凭据。
- 上传在写盘前校验工具、文件数量、单文件大小和总大小，采用分块写入与临时文件原子替换；异常不会把内部堆栈返回客户端。
- 媒体本地路径会解析后校验仍位于 `backend/static` 下；远程媒体下载只接受 HTTPS，并拒绝回环、私网、链路本地、保留地址和云元数据主机名。
- 工具生图任务进入持久 `TaskRun`，由统一调度器恢复；进程重启不会遗留永远处于 `queued/running` 的内存协程。
- 管理员调整余额使用数据库行锁；漫剧 Agent 聊天写入用量前会校验项目归属。
- Postgres 与 Redis 在根目录 Compose 中不映射宿主端口，Redis 使用必填密码；独立中间件 Compose 仅绑定 `127.0.0.1`。
- 注册、登录、找回密码和重置密码在单进程内有按直接连接地址的 60 秒窗口限制；生产仍应在反向代理/API 网关配置共享限流，避免多副本各自计数。
- 生产设置 `MEDIA_REQUIRE_SIGNATURE=true` 后，`/static/generated/...` 的旧无签名入口返回 403，应用生成的本地媒体 URL 改为 `/api/media/generated/...` 的短期 HMAC capability；API JSON 响应边界会刷新历史已过期的本地媒体 URL。OSS URL 在启用 OSS 时使用对象存储短期签名；模板、mock、site 静态资源仍可公开读取。

## 部署前必须完成

1. 从 `deploy/.env.docker.example` 或 `deploy/.env.prod.example` 复制环境文件，并替换所有 `replace-with-*` 值。密码建议使用 URL 安全字符，避免把 `@`、`:`、`/` 直接放进数据库或 Redis URL。
2. 生产设置 `ENVIRONMENT=production`、随机 `SECRET_KEY`、真实 `POSTGRES_PASSWORD` 和 `REDIS_PASSWORD`。不要把 `.env`、密钥、OSS 密钥或支付密钥加入版本库。
3. 通过反向代理提供 HTTPS；`CORS_ORIGINS` 只保留实际前端来源。不要把 `allow_origins=*` 与带凭据的跨域请求一起使用。
4. 定期备份 `printfilm_pgdata` 和 `printfilm_media`，并演练恢复。Redis 只保存队列/进度，不能替代数据库备份。
5. 生产发布后先访问 `/api/health`，再用管理员令牌访问 `/api/health/details`，核对数据库池、任务运行时和请求错误计数。

## 当前边界与剩余风险

- `generated` 的 capability 当前证明持有短期签名即可读取，未绑定用户或项目；若需要强租户隔离，应在 `/api/media` 查询数据库 owner 后再签发 URL。目录名校验、路径归属和签名能防止任意文件读取，但不替代租户授权。
- 生产环境仍建议单 worker 运行 API，因为任务运行时是进程内调度器；需要多副本时应先把任务执行器、租约和媒体访问迁移到独立服务，并验证幂等与租约语义。
- 上传限制保护应用层资源，但 Nginx 的 `client_max_body_size` 也必须与应用限制一致；当前默认值为 512 MB，应用默认单文件 40 MB、总量 160 MB。

## 事件排查

使用响应头中的 `X-Request-ID` 搜索 API 日志；任务故障使用 `TaskRun.id`、`provider_task_id` 和对应的 `UsageEvent.task_run_id` 关联。不要在日志、工单或截图中粘贴 Authorization、API Key、支付签名或完整远程 URL 查询参数。
