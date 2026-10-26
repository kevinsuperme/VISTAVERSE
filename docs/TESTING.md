# 万象影界 | VISTAVERSE 测试与质量门禁

## 本地命令

后端：

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m compileall -q app tests
pytest -q --cov=app --cov-report=term-missing
```

带 `db_session` 的测试需要 PostgreSQL。测试夹具会从 `DATABASE_URL` 派生独立的 `<database>_test` 数据库，并在外层事务回滚；不要把生产库 URL 直接用于测试。TokenFree 价目和账单网络调用在测试中被 stub。

Windows 本机可复用 Docker 中的 PostgreSQL / Redis，API 仍由宿主机源码进程
运行。默认映射端口为 PostgreSQL `127.0.0.1:15432`、Redis
`127.0.0.1:16379`；连接串示例和启动顺序见
[../deploy/README.md](../deploy/README.md) 的“本机源码 API 调试”。建议先执行
下面的定向回归，再执行完整后端套件：

```powershell
cd backend
python -m compileall -q app tests
python -m pytest -q tests/test_kepu_shot_edit_demote.py
python -m pytest -q
```

定向测试覆盖科普旁白/连续音频编辑后的项目阶段回退；若该测试失败，先检查
`backend/app/api/projects.py` 的 `_demote_after_edit()` 与阶段解析逻辑，再扩大
测试范围。测试通过只表示代码和隔离数据库路径通过，不代表真实 TokenFree、OSS、
FFmpeg 或支付回调已经联调。

用户端和管理端：

```bash
cd frontend && npm ci && npm test && npm run lint && npm run build
cd ../admin && npm ci && npm test && npm run lint && npm run build
```

管理端本轮回归还包括 `admin/tests/settingsPersistence.test.mjs`、`admin/tests/templateValidation.test.mjs`，用于设置保存失败保留草稿、保存响应复用、模板字段校验和危险 URL 拦截。

浏览器验收可使用已安装的 Python Playwright 与本地 Chrome，在 `admin` 开发服务器上执行登录页、深链回跳及 375px 移动视口检查。截图和临时日志放在被忽略的 `.tmp/admin-acceptance/`，不提交凭据。本轮实际执行：`python admin/tests/browser_acceptance.py --base-url http://127.0.0.1:5174`，真实 Chrome + 明确 API fixtures 共 88/88 通过，`page_errors=0`、`console_errors=0`、`unknown_api_contracts=0`；这不是生产后端联调结果。

后端管理端纯权限/导出/幂等回归：

```powershell
F:\VISTAVERSE\.venv\Scripts\python.exe .tmp\admin-acceptance\run_backend_tests.py tests/test_admin_permissions_exports.py tests/test_phase2_reliability.py -q
```

需要 PostgreSQL 的集成测试必须使用独立数据库；Docker daemon、镜像和健康检查均通过后再运行完整套件。数据库未启动时应报告环境阻塞，不能把纯单测结果表述为数据库联调通过。

## CI

`.github/workflows/ci.yml` 在 push 和 pull request 上执行：Python 3.12 + PostgreSQL 集成测试、coverage 报告、前端/管理端纯测试、oxlint 和 TypeScript/Vite 构建。CI 使用临时数据库和 mock 上游，不代表真实 TokenFree、OSS、FFmpeg 或支付回调已经联调通过。

## 验证边界

- `compileall` 只证明 Python 语法可编译。
- 单元测试覆盖状态机、鉴权回跳、任务执行和上传边界；需要真实 PostgreSQL 的测试还验证锁、事务和 schema。
- `npm run build` 不等于浏览器验收；发布前仍需检查登录回跳、支付轮询取消、画布离开页面保存和媒体播放。
- 真实上游、OSS、支付、FFmpeg 和 Docker 网络需要单独的受控联调环境，不应在 CI 中使用生产凭据。
