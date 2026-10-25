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

## CI

`.github/workflows/ci.yml` 在 push 和 pull request 上执行：Python 3.12 + PostgreSQL 集成测试、coverage 报告、前端/管理端纯测试、oxlint 和 TypeScript/Vite 构建。CI 使用临时数据库和 mock 上游，不代表真实 TokenFree、OSS、FFmpeg 或支付回调已经联调通过。

## 验证边界

- `compileall` 只证明 Python 语法可编译。
- 单元测试覆盖状态机、鉴权回跳、任务执行和上传边界；需要真实 PostgreSQL 的测试还验证锁、事务和 schema。
- `npm run build` 不等于浏览器验收；发布前仍需检查登录回跳、支付轮询取消、画布离开页面保存和媒体播放。
- 真实上游、OSS、支付、FFmpeg 和 Docker 网络需要单独的受控联调环境，不应在 CI 中使用生产凭据。
