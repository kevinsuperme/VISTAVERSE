# 万象影界 | VISTAVERSE 安全基线与威胁边界

本文描述当前代码可验证的安全约束，以及部署者必须承担的配置责任。它与 `docs/STANDARDS.md` 一起作为发布前检查清单。

## 已落实的基线

- `ENVIRONMENT=production`、`prod` 或 `staging` 启动时，`SECRET_KEY` 必须至少 32 个字符，且不能使用示例值；已填写的 TokenFree、支付、SMTP、TOS 或 OSS 凭据也不能使用示例占位值；数据库连接串也不能使用仓库示例密码。
- 开发环境不配置密钥时只生成一次性随机密钥，重启会使本地会话失效。生产环境不会自动生成密钥。
- 开发诊断接口刷新配置时复用当前进程的一次性密钥，不会因为读取健康详情而主动注销现有会话。
- 生产环境默认关闭 FastAPI `/docs`、`/redoc` 和 `/openapi.json`。需要开放接口文档时，应在受控的内网或已认证反向代理后单独开放。
- 公共 `/api/health` 只返回存活状态，`/api/ready` 以 200/503 表示数据库、Redis 和任务运行时就绪；数据库连接池、任务运行时、媒体磁盘、模型名和请求统计位于需要管理员身份的 `/api/health/details`。
- 每个 HTTP 响应带 `X-Request-ID`。客户端提供的值仅在可打印 ASCII、长度不超过 64 时复用，否则生成随机值；该值用于日志关联，不是鉴权凭据。
- 上传在写盘前校验工具、文件数量、单文件大小和总大小，采用分块写入与临时文件原子替换；异常不会把内部堆栈返回客户端。
- 媒体本地路径会解析后校验仍位于 `backend/static` 下；远程媒体下载只接受 HTTPS，并拒绝回环、私网、链路本地、保留地址和云元数据主机名。
- 工具生图任务进入持久 `TaskRun`，由统一调度器恢复；进程重启不会遗留永远处于 `queued/running` 的内存协程。
- 管理员调整余额使用数据库行锁；漫剧 Agent 聊天写入用量前会校验项目归属。
- 支付回调和用户手动关单共用订单行锁；回调缺失或非法 `money` 会失败关闭，不会回退到订单金额。
- 漫剧音色生成通过 `voice_synthesis` 轻量任务执行，沿用预扣、用量记录和结算链路；非法角色关联会在写入生成状态前拒绝。
- 任务取消在计费行锁后再次检查；取消会清理租约、写入 `task.cancelled` 事件并结算冻结余额。
- 注册邮箱统一规范化；并发唯一键冲突会回滚并返回“邮箱已注册”，不会泄露数据库异常。
- Postgres 与 Redis 在根目录 Compose 中不映射宿主端口，Redis 使用必填密码；独立中间件 Compose 仅绑定 `127.0.0.1`。
- 注册、登录、找回密码和重置密码在单进程内有按直接连接地址的 60 秒窗口限制；生产仍应在反向代理/API 网关配置共享限流，避免多副本各自计数。注册和资料邮箱更新均规范化并处理唯一键竞态。
- 生产设置 `MEDIA_REQUIRE_SIGNATURE=true` 后，`/static/generated/...` 的旧无签名入口返回 403，应用生成的本地媒体 URL 改为 `/api/media/generated/...` 的短期 HMAC capability；API JSON 响应边界会刷新历史已过期的本地媒体 URL。OSS URL 在启用 OSS 时使用对象存储短期签名；模板、mock、site 静态资源仍可公开读取。
- `X-Forwarded-For` / `X-Real-IP` 默认不可信；只有请求直连对端命中 `TRUSTED_PROXY_IPS`（CIDR 逗号列表）时才读取这些头。代理必须先清洗客户端自带的 XFF，应用仍需按可信链取值，避免客户端伪造支付 clientip。

## 部署前必须完成

1. 从 `deploy/.env.docker.example` 或 `deploy/.env.prod.example` 复制环境文件，并替换所有 `replace-with-*`、`your-*` 和 `*.example` 占位值。`OPENAI_API_KEY` / `ARK_API_KEY` 可以留空并在管理后台填写真实密钥；密码建议使用 URL 安全字符，避免把 `@`、`:`、`/` 直接放进数据库或 Redis URL。
2. 生产设置 `ENVIRONMENT=production`、随机 `SECRET_KEY`、真实 `POSTGRES_PASSWORD` 和 `REDIS_PASSWORD`。不要把 `.env`、密钥、OSS 密钥或支付密钥加入版本库。
3. 通过反向代理提供 HTTPS；`CORS_ORIGINS` 只保留实际前端来源。不要把 `allow_origins=*` 与带凭据的跨域请求一起使用。
4. 定期备份 `printfilm_pgdata` 和 `printfilm_media`，并演练恢复。Redis 只保存队列/进度，不能替代数据库备份。
5. 生产发布后先访问 `/api/health` 和 `/api/ready`，再用管理员令牌访问 `/api/health/details`，核对数据库池、任务运行时和请求错误计数。

## 当前边界与剩余风险

- 当前 `get_current_user` 同时接受 JWT 与 `pf_live_` API Key，但 API Key 产品契约仅覆盖 `/api/v1`；因此持有普通 Key 可访问项目、计费、任务和用户 Key 管理路由，管理员 Key 还可通过 `get_current_admin` 访问管理路由。应拆分 JWT-only 依赖与带 scope 的 API Key 依赖，默认拒绝 Key 访问敏感/管理接口。
- `generated` 的 capability 当前证明持有短期签名即可读取，未绑定用户或项目；若需要强租户隔离，应在 `/api/media` 查询数据库 owner 后再签发 URL。目录名校验、路径归属和签名能防止任意文件读取，但不替代租户授权。
- 普通项目与漫剧项目仍使用 `generated/p{id}` 共享目录；当前同 ID 且不同 owner 时拒绝签发，长期应迁移到带 domain/UUID 的目录并迁移旧媒体。
- JWT 目前只含 `sub/exp`，改密或重置密码后旧令牌在到期前仍有效；如需立即撤销，应增加 `token_version` 或密码变更时间校验。
- 生成 API、工具 API 和漫剧生成仍需在网关或 Redis 层补充按用户/API key/IP 的分布式限流与每日额度；当前登录相关限流不覆盖所有上游消耗入口。
- 启动迁移仍由 `backend/app/main.py` 的版本检查和补丁执行，当前版本为 2；新增补丁必须 bump 版本。旧任务列清理和时间列类型统一应迁移到可审计的版本化 migration，禁止把启动 DDL 当作长期迁移系统。
- 外部 HTTPS URL 的解析校验与后续 HTTP 连接之间仍存在 DNS rebinding 窗口；高安全部署应通过固定解析的 HTTP 客户端或 egress proxy 收敛。
- 新上传 OSS 对象显式使用 `private` ACL；签名失败会报错而不回退公开 URL。已有 `public-read` 对象及 bucket policy 不会被本次代码修改自动收紧：上线前需盘点旧 ACL，在授权和回滚方案下单独迁移，并验证无签名访问 403、有效签名 200、过期签名 403。静态站点发布如复用此上传器，需要改为受控 CDN/origin 策略，不能依赖旧 public-read 行为。
- 前端 JWT 仍保存在 `localStorage`，Nginx 默认未统一下发 CSP、`X-Frame-Options`、`nosniff` 和 `Referrer-Policy`；公网部署前应迁移 HttpOnly cookie 或严格 CSP，并补齐响应头。
- `ark.py`、`studio_tools.py` 和漫剧参考音频流程仍有未统一超时的 FFmpeg 子进程；需统一进程组终止和资源上限，避免单 worker 被外部媒体拖住。
- 实际用量高于预扣估算时结算路径可能出现余额透支；应定义欠费状态或额度上限，而不是允许钱包余额变负。
- 部分漫剧接口仍把 `str(exc)` 写入客户端或资产参数，剧本/画布 JSON 的数量与总大小约束也需统一补齐。
- 生产环境仍建议单 worker 运行 API，因为任务运行时是进程内调度器；需要多副本时应先把任务执行器、租约和媒体访问迁移到独立服务，并验证幂等与租约语义。
- 上传限制保护应用层资源，但 Nginx 的 `client_max_body_size` 也必须与应用限制一致；当前默认值为 512 MB，应用默认单文件 40 MB、总量 160 MB。

## 事件排查

使用响应头中的 `X-Request-ID` 搜索 API 日志；任务故障使用 `TaskRun.id`、`provider_task_id` 和对应的 `UsageEvent.task_run_id` 关联。不要在日志、工单或截图中粘贴 Authorization、API Key、支付签名或完整远程 URL 查询参数。

## 本轮收紧的边界

头像不再相信文件名或 MIME：分块接收、5 MiB 输入上限、真实图片解码与 16M 像素/8192 边长限制，再生成最多 1024 像素 PNG，清除原始元数据、动画和尾随内容；解码与文件发布在工作线程执行。旧头像文件不会自动删除，需要按引用关系和保留周期单独清理。

应用日志在最终格式化后统一脱敏 URL（包括异常堆栈）、查询串和邮箱；Uvicorn access/error handler 同样接入。仓库 Nginx access log 仅记录路径，不写 `$request`/`$args`；宿主机额外反向代理、第三方 APM、SDK 自建 handler 和旧日志仍需单独核查，不能视为自动追溯清理。Nginx 明确拒绝 dotfile（保留 `.well-known`）、数据库备份、私钥及开发配置路径，避免 SPA fallback 将探测伪装为 200。

生产验收和备份恢复报告要求见 [PRODUCTION_VERIFICATION.md](PRODUCTION_VERIFICATION.md)；所有真实上游调用、对象 ACL 修改、备份生成与隔离恢复都必须按实际环境授权执行，文档不宣称已完成演练。

项目封面、分镜、工具及漫剧图片执行真实解码与 PNG 重编码，保留原图尺寸但限制 16M 像素/8192 边长；漫剧音频和工具视频通过最多 15 秒的本地 `ffprobe` 校验实际容器、轨道和时长（最长 1 小时）。工具视频允许音轨，拒绝附件、字幕和数据流。协议仅允许 file/pipe，校验失败清理临时文件。媒体结构校验不是恶意软件扫描；线上 FFmpeg/ffprobe 可用性仍须在构建后验证。
