# VISTAVERSE | Codex 项目配置与审核规范

本仓库的产品品牌是“万象影界 | VISTAVERSE”，技术代号仍为 `PRINTFILM` / `printfilm`。项目级 Codex 配置位于
`.codex/`，仓库技能位于 `.agents/skills/`，两者均不包含凭据。

## 配置内容

- `.codex/config.toml`：项目级并发代理默认值，以及可选的 OpenAI Developers Docs MCP（无凭据、非必需、提示式工具审批）。
- `.codex/agents/architecture-reviewer.toml`：架构、模块边界和数据流证据审查。
- `.codex/agents/security-reviewer.toml`：认证、密钥、媒体访问、供应链和 CI 安全审查。
- `.codex/agents/deployment-reviewer.toml`：Compose、镜像、卷、健康检查、回滚和服务器运维审查。
- `.agents/skills/vistaverse-operations/`：本项目的构建、发布、启动、停止、日志、健康检查、备份、回滚和故障路由。
- `.agents/skills/vistaverse-review/`：多角色交叉审核的证据格式、优先级和验证边界。

Codex 项目配置只覆盖仓库行为；provider、认证、遥测和个人全局设置仍由用户级配置管理。MCP 服务只是文档查询
辅助能力，不替代本地代码事实、项目测试或 Docker 验证；离线时它可以不可用而不阻塞项目任务。

## 与项目工具链的对应关系

| 领域 | 本项目事实 | 配置/技能约定 |
| --- | --- | --- |
| 后端 | Python 3.12、FastAPI、SQLAlchemy、PostgreSQL 16、Redis 7 | `architecture_reviewer`、`security_reviewer`；运行一条真实健康路径 |
| 前端 | React 19、TypeScript 6、Vite 8、Node 22 | `npm test`、`npm run lint`、`npm run build` |
| 媒体 | FFmpeg、文泉驿中文字体、持久化媒体卷 | 运维技能检查字体、磁盘和生成目录 |
| 容器 | Docker Compose 全栈或中间件 + 宿主机 API | `deployment_reviewer`；先 `config --quiet`，再有界启动 |
| CI | GitHub Actions，PostgreSQL 服务，后端覆盖率门槛 35% | 以 `.github/workflows/ci.yml` 为准，不把本地通过冒充 CI 通过 |
| 外部服务 | TokenFree/ARK、OSS、SMTP、Epay（按环境变量启用） | 不在配置或报告中写入实际密钥；逐项记录缺失变量名 |

## 审核和验证命令

```powershell
git status --short
docker context show
docker compose -f docker-compose.yml --env-file deploy/.env.docker config --quiet
docker compose -f docker-compose.full.yml --env-file deploy/.env.docker config --quiet
python -m compileall -q backend/app backend/tests
Set-Location backend; python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=35
Set-Location ..\frontend; npm test; npm run lint; npm run build
Set-Location ..\admin; npm test; npm run lint; npm run build
```

后端测试必须使用已安装 `backend/requirements-dev.txt` 的 Python 环境，并需要可用的 PostgreSQL 测试服务；缺失依赖
或服务时要明确记录为环境阻塞。构建成功不等于已验证登录、任务、媒体签名或管理员流程。

## 本次交叉审核快照

架构、后端功能、安全/供应链、测试和部署运维角色已按本地代码、Compose、CI、脚本和文档交叉复核。已直接修复的高影响问题包括：

- 订单回调/手动关单竞态、非法支付金额回退、代理 IP 伪造和注册邮箱唯一键竞态。
- `/api/v1` 远程媒体 URL 的 HTTPS/DNS/内网地址校验、Seedance 输入上限、头像/封面分块上传和 FFmpeg 超时。
- 任务去重、取消前计费锁复查、冻结余额结算、租约清理与取消事件；漫剧音色生成纳入 `voice_synthesis` 计费任务。
- Redis 同步调用移出 FastAPI 事件循环、上游错误统一为通用客户端消息，以及媒体 ID 碰撞时 fail-closed。

验证快照（2026-10-25，本机 `desktop-linux` Docker context）：

- 后端 Python 3.12：`890 passed, 1 skipped`，覆盖率 `56.43%`，CI 门槛为 35%。
- 用户端：测试 10/10，lint exit 0（既有 hooks/Fast Refresh 警告），Vite 构建通过；主压缩包约 1.18 MB。
- 管理端：测试 9/9，lint exit 0（既有警告），构建通过；主压缩包约 971 KB。
- 三套 Compose `config --quiet`、Python 编译检查和两项仓库技能 `quick_validate.py` 均通过；Postgres/Redis healthy，Web/Admin 返回 200，宿主 API `/api/health` 返回 200。
- API Docker 镜像本轮未完成构建：构建在 Debian apt 元数据下载阶段受网络/镜像源阻塞；因此没有把宿主 API 健康结果冒充 API 容器验证。

仍需单独排期的风险：API Key 与 JWT 依赖边界及 scope、JWT 无主动撤销、生成入口的分布式限流、`generated/p{id}` 跨域命名空间迁移、启动 DDL 版本化与时间列迁移、批量 ZIP 峰值、Seedance 临时文件清理、部分漫剧错误原文和 OSS 公开 ACL 策略。详见 [SECURITY.md](./SECURITY.md) 与 [OPERATIONS.md](./OPERATIONS.md)。

## 服务器操作边界

完整操作命令、最低资源建议、备份和回滚规则见 `.agents/skills/vistaverse-operations/references/runbook.md`、
`docs/OPERATIONS.md` 和 `docs/SECURITY.md`。默认只停止项目范围服务、保留卷；清理时仅删除确认可重建的缓存或产物，
不删除密钥、数据库、媒体卷、运行数据或用户文件。
