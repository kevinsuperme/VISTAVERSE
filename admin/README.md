# 万象影界 | VISTAVERSE 管理后台

管理端用于用户、订单与流水、内容审核、漫剧资产、模板、任务和运行设置管理。它是独立的 React 19 + TypeScript + Vite 8 SPA，生产环境挂载在 `/admin/`，开发环境默认运行在 `http://127.0.0.1:5174/`。

## 开发与构建

```powershell
npm ci
npm run dev
npm test
npm run lint
npm run build
```

开发服务器将 `/api` 和 `/static` 代理到 `http://127.0.0.1:8000`。生产构建使用 `/admin/` base，部署时由现有 Nginx/Compose 服务提供静态文件。

## 登录与权限

登录后管理端启动会调用 `/api/auth/me`，服务端角色和 `permissions` 决定路由及操作入口；localStorage 只作为会话缓存，不能替代后端鉴权。页面的审核、调账、批量修改和设置保存都由后端再次校验。

角色矩阵、通知接口和导出限制见 [`docs/ADMIN_CONSOLE.md`](../docs/ADMIN_CONSOLE.md)。管理员操作不得把 token、密码或 secret 写入 URL、导出文件或日志。

## 目录约定

- `src/pages/`：按路由拆分的页面，使用 React.lazy 做路由级分包。
- `src/components/admin/`：列表状态、Drawer、确认、导出和通知等管理端组件。
- `src/hooks/`：URL 筛选、请求竞态和设置持久化等共享逻辑。
- `src/styles/`：tokens、壳层、组件、设置、模板、任务和响应式样式；`index.css` 只负责按顺序导入。
- `tests/`：不依赖浏览器的状态、校验和设置持久化回归测试。

管理端遵循服务端分页、加载/空/错状态、危险操作二次确认、键盘可操作和移动端抽屉布局约定。
