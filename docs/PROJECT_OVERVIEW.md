# 万象影界 | VISTAVERSE 项目说明

> **一句话定位**：从一段文字，到一部好片。  
> **品牌主张**：**一念成片，万象可见。**  
> **技术代号**：`PRINTFILM` / `printfilm`

本文是万象影界的项目总览，说明产品边界、主要模块、核心流程、运行入口、数据流、依赖关系和验证方式。仓库目录、镜像名、环境变量、数据库表与 API 路径继续使用 `PRINTFILM` / `printfilm`，这是兼容性要求，不代表对外品牌仍使用旧名称。

品牌 Logo、色彩、语气和产品命名见 [brand-guidelines.md](./brand-guidelines.md)。

当前标准视觉资产为 `frontend/public/logo.png` 与 `frontend/public/hero-3.png`；
`logo.svg` 是不依赖 PNG 的纯矢量 Logo；`hero.jpg` 作为旧主视觉路径的兼容入口。

## 1. 产品能力

万象影界是面向创作者和内容团队的 AI 内容片场，当前包含四类能力：

| 产品线 | 能力 | 产物 |
|---|---|---|
| AI 漫剧 | 项目、分集、剧本、角色/场景/道具资产、分镜画布 | 可连续制作的分集与分镜任务 |
| AI 短视频 | 模板、主题/口播、自动拆镜、图像、视频、旁白与合成 | 适合科普、获客和宣传的短片 |
| 工具中心 | 文生图、图生图、图生产品、文生视频、视频生视频、电商拼图 | 单点生成任务 |
| 管理与开放能力 | 用户、订单、模板、任务、模型路由、计费、`/api/v1` | 运营数据与程序化调用 |

主要宣传语：

- 中文：**一念成片，万象可见。**
- 英文：**Turn Every Idea into a World.**
- 产品描述：**AI Story & Film Studio**

## 2. 技术栈和目录

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、SQLAlchemy 2、asyncpg、PostgreSQL、Redis |
| 用户端 | React 19、TypeScript、Vite 8、语义化 CSS |
| 管理端 | React 19、TypeScript、Vite 8、Tailwind v4、Radix/shadcn 风格组件 |
| 生成服务 | TokenFree New API（文本、图像、视频）；Seedance 负责视频口播能力 |
| 媒体处理 | FFmpeg / ffprobe；本地落盘，可选 OSS 异步上传 |
| 任务运行 | FastAPI 进程内 scheduler、executor、poller、watchdog，无独立 Celery worker |
| 部署 | 根目录 Compose 全栈镜像，或 Docker 中间件 + 宿主机源码 API |

```text
backend/                  FastAPI、领域 API、流水线、计费、任务运行时
frontend/                 创作者用户端
admin/                    运营管理端
deploy/                   环境示例、中间件 Compose、部署脚本
docs/                     产品规则、工程规范、运行与测试文档
docker-compose.yml        公开镜像全栈运行入口
docker-compose.full.yml   从源码构建全栈镜像入口
```

## 3. 核心业务流程

### 3.1 AI 短视频

```text
主题 / 脚本
  → 模板与风格
  → LLM 生成或规范化分镜
  → 分镜图
  → 分镜视频（full 模式）
  → Seedance 口播或后期旁白
  → FFmpeg 合成、字幕、BGM
  → 本地媒体 / OSS 成片
```

`full` 模式执行图像、视频和成片；`image_text` 模式使用静图、字幕和旁白，跳过 AI 视频。单镜编辑会清理受影响的下游媒体；旁白真实变化会使整片连贯音轨失效并回退到脚本阶段。

### 3.2 AI 漫剧

```text
项目
  → 大纲 / 剧情摘要 / 剧本
  → 分集
  → 角色、场景、道具、音色资产
  → 结构化分镜与画布
  → 一镜一视频任务
  → 预览、审核、导出
```

分集规则以 [EPISODE_RULES.md](./EPISODE_RULES.md) 为准，镜头拆分和参考素材约束见 [SHOT_SPLITTING.md](./SHOT_SPLITTING.md) 与 [SEEDANCE_2_5.md](./SEEDANCE_2_5.md)。

## 4. 关键入口和模块依赖

### 后端入口

- `backend/app/main.py`：FastAPI 应用、启动/关闭生命周期、数据库初始化、增量 schema migration、内置模板与 Skill seed。
- `backend/app/api/`：HTTP 鉴权、参数校验、领域路由；业务逻辑下沉到 `services/`。
- `backend/app/services/pipeline.py`：科普流水线编排、恢复计划和 FFmpeg 合成调用。
- `backend/app/services/kepu_stages.py`：`script | assets | videos | compose` 阶段唯一判定源，供计费预扣和流水线恢复共同使用。
- `backend/app/services/tasks/`：任务创建、调度、执行、轮询、租约和看门狗。
- `backend/app/services/drama/` 与 `backend/app/api/drama/`：漫剧项目、分集、分镜、资产和视频任务。
- `backend/app/services/billing/`：估价、冻结、用量、结算、退款和支付回调。
- `backend/app/services/storage.py`、`media_access.py`、`oss.py`：本地媒体路径、签名 URL 和可选 OSS。

### 前端入口

- 用户端入口：`frontend/src/main.tsx`、`frontend/src/App.tsx`。
- 用户端公共请求：`frontend/src/api.ts` 与 `frontend/src/api/`。
- 用户端品牌壳层：`frontend/src/components/layout/`、`frontend/src/components/BrandMark.tsx`。
- 管理端入口：`admin/src/main.tsx`、`admin/src/App.tsx`。
- 管理端壳层：`admin/src/components/layout/AdminLayout.tsx`。

### 依赖关系

```text
React 用户端 ─┐
              ├─ HTTP/SSE ─→ FastAPI API ─→ SQLAlchemy/ PostgreSQL
React 管理端 ─┘                  │        └→ Redis（进度与队列桥）
                                 ├─→ Task Runtime（scheduler/executor/poller）
                                 ├─→ TokenFree / Seedance 上游
                                 └─→ Storage → FFmpeg → 本地媒体 / OSS
```

数据库是项目、用户、任务、计费和配置的事实来源；Redis 用于进度、队列辅助和短期运行状态，不能替代 PostgreSQL 备份。运行时配置以管理后台数据库 overlay 优先，环境变量用于首次启动和基础安全配置。

## 5. 数据流和状态边界

1. 浏览器提交项目、分镜或工具请求。
2. API 完成身份、权限、额度和参数校验，创建 `TaskRun` 及其 steps/events/targets。
3. scheduler 获取到期任务并受全站、单用户并发槽位限制；executor 执行 handler；poller 统一轮询上游任务。
4. 上游响应写入任务事件和用量证据，成功后进入结算；失败会记录可检索的错误和重试状态。
5. 媒体先写入 `backend/static/generated/p{id}/`，生产环境通过 `/api/media/...` 签发短期签名地址；开启 OSS 后再由异步队列上传。
6. 前端通过状态接口和 SSE/进度桥刷新页面；页面离开不等于任务取消。

项目状态、分镜状态、任务状态和计费状态分别由服务端模型维护。前端只能展示服务端状态，不能将本地进度当作任务完成事实。

## 6. 运行方式

### 6.1 全栈 Docker

```bash
cp deploy/.env.docker.example deploy/.env.docker
# 修改数据库密码、Redis 密码、SECRET_KEY 和 API Key
docker compose --env-file deploy/.env.docker -f docker-compose.yml -f deploy/release.lock.yml up -d --no-build
```

地址：用户端 `http://localhost:8080`、管理端 `http://localhost:8081`、API `http://localhost:8000`。生产模式默认关闭 `/docs`、`/redoc` 和 `/openapi.json`，媒体签名由 `MEDIA_REQUIRE_SIGNATURE=true` 控制。

### 6.2 Windows 本机源码调试

推荐把 PostgreSQL 和 Redis 放在 `deploy/docker-compose.yml`，API 使用宿主机 Python 源码运行：

```powershell
docker compose -p printfilm-local-middleware `
  -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

宿主机连接端口为 PostgreSQL `15432`、Redis `16379`。若已有与当前提交对应的 `printfilm-web:<release-tag>` 与 `printfilm-admin-web:<release-tag>`，可使用 `api:host-gateway` 将静态站点容器反代到宿主机 API，具体命令见 [deploy/README.md](../deploy/README.md)。

## 7. 测试与质量门禁

后端依赖 Docker PostgreSQL/Redis 时，在 `backend/` 执行：

```powershell
python -m compileall -q app tests
python -m pytest -q tests/test_kepu_shot_edit_demote.py
python -m pytest -q
```

用户端和管理端分别执行：

```bash
cd frontend && npm test && npm run lint && npm run build
cd ../admin && npm test && npm run lint && npm run build
```

测试夹具会派生独立的 `<database>_test` 数据库，并回滚每个用例事务；真实 TokenFree、OSS、FFmpeg 和支付回调需要单独的受控联调环境。

## 8. 工程边界与主要风险

- 任务运行时在 API 进程内，生产建议单 worker；多副本部署前必须确认租约、迁移和任务恢复策略。
- 生成质量、上游限流、模型可用性和计费金额仍受 TokenFree / Seedance 实际响应影响。
- 本地媒体依赖磁盘空间和 FFmpeg/中文字体；OSS 上传失败时应保留本地文件并观察异步队列。
- `ENVIRONMENT=production` 下的 API 文档关闭和媒体签名是安全默认值，调试时不要用真实生产密钥。
- 完整 API 镜像构建可能受 Docker Hub、Debian 或 PyPI 下载限制；镜像未验证时使用中间件容器 + 宿主机源码 API，并明确记录验证边界。

安全配置见 [SECURITY.md](./SECURITY.md)，运行与升级见 [OPERATIONS.md](./OPERATIONS.md)，测试命令见 [TESTING.md](./TESTING.md)。

