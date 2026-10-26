# 管理后台功能与权限说明

## 页面与业务入口

`admin/src/App.tsx` 使用 React.lazy 按页面拆包，`RequireAdmin` 在渲染管理壳前请求 `/api/auth/me`。列表页面的筛选、页码和主要 Tab 写入 URL，刷新或复制深链后仍可恢复上下文；订单、作品、用户详情使用精确 ID 请求，避免只在当前分页查找。

统一交互由以下组件提供：

- `AdminFilterBar`、`AdminSearchInput`、`PaginationBar`：筛选、搜索、分页及 ARIA 状态。
- `AdminListState`、`useAdminRequest`：加载、空结果、错误重试和旧请求丢弃。
- `AdminModal`：对话框/右侧 Drawer；窄屏 Drawer 使用全宽高度，危险写操作由 `AdminConfirmDialog` 且在请求中锁定关闭。
- `AdminNotifications`：读取真实失败任务、待审核和运行异常通知；已读状态使用后端持久化接口。
- `AdminExportButton`：携带 Authorization 下载后端 CSV，后端限制最多 10000 行并过滤公式注入。

列表 URL 更新统一经 `updateAdminQuery` 合并同一事件中的筛选、分页和详情参数，避免 React Router 连续导航丢失上下文。用户详情 Drawer 会先展示当前列表行快照，再用用户 ID 精确接口刷新；刷新失败时保留可用快照并允许重试。

审核操作支持单条和最多 50 条批量处理，拒绝必须填写原因，响应保留逐项成功/失败结果。调账要求独立确认、备注和审计信息；前端请求中禁用重复提交，后端使用收据和用户行锁保证带请求编号的调账幂等。

## 角色权限矩阵

后端权限单一真相源位于 `backend/app/services/admin/permissions.py`，未知管理路由默认拒绝。`admin` 拥有全部权限；其余角色如下：

| 角色 | 允许范围 |
| --- | --- |
| `admin_readonly` | 仪表盘、用户/订单/财务/任务/内容/作品/模板/通知只读 |
| `admin_operator` | 只读范围 + 用户套餐、任务取消、模板写入；不能调账或提权 |
| `admin_finance` | 财务、订单、用户只读、余额调账、财务同步、通知和仪表盘聚合 |
| `admin_reviewer` | 作品审核、内容和模板只读、通知；无仪表盘，登录后进入作品审核 |

用户角色修改和系统设置写入只能由 `admin` 执行。未登记的管理路由对所有角色（含 `admin`）默认拒绝；新增 API 必须同时登记权限。`get_current_admin` 每次从数据库读取用户，角色变更在下一请求生效；前端隐藏入口只用于减少误操作，不能视为安全边界。

本轮权限按业务模块划分。`content:read` 可查看内容关联的作者信息和消费数据，`works:read` 可查看作品作者邮箱；这不是按字段隔离的财务脱敏方案。`admin_finance` 的仪表盘包含项目数量、状态和用量聚合，但不能访问无 `content:read` 或 `tasks:read` 权限的内容/任务详情。`content:write` 是预留权限，当前管理 API 没有对应内容写入路由。

部署环境的 `ADMIN_BOOTSTRAP_EMAILS` 保留原有管理员恢复行为：每次 API 启动都会将名单内已注册账号提升为 `admin`，即使后台先前把它改为只读或其他角色。需要持久降权时，先从该环境变量名单移除账号，再调整角色；仅修改数据库角色不能覆盖启动配置。

## 接口约定

- 精确详情：`GET /api/admin/users/{id}`、`/works/{id}`、`/orders/{id}`。
- 审核批量：`POST /api/admin/works/bulk`，最多 50 个 ID，返回 `results/succeeded/failed`。
- 模板批量：`POST /api/admin/templates/bulk`，支持批量上下架。
- 通知：`GET /api/admin/notifications?page=&page_size=&unread_only=`、`PATCH /api/admin/notifications/read`。
- 导出：works、templates、finance 使用与列表相同的筛选，服务端限制 10000 行。

新增表 `admin_audit_logs`、`admin_notification_reads`、`admin_balance_requests` 由 `init_db()` 注册；作品审核字段通过 `backend/app/main.py::_apply_schema_patches()` 的版本迁移（当前版本 2）补齐。角色、余额、审核、模板变更和审计在同一事务提交；审计只保存选定字段，不保存模型配置或完整请求体。

调账 PATCH 接受 `balance_request_id`（UUID）和 `expected_balance_fen`（确认时余额）：相同操作人/用户/请求编号及内容重试，只返回当前用户状态，不重复记账；相同编号不同金额、备注或快照返回 `409`。新编号的余额快照不匹配也返回 `409`，必须重新读取用户余额并确认。前端网络失败重试复用编号，修改表单内容后生成新编号；不能自动换编号重放一次结果未知的原请求。幂等收据只保存内容 SHA-256 和结果余额，与钱包流水同事务提交。旧客户端可以不带这两个字段，保留原行为，但不获得重试幂等保证；所有非零调账均需非空备注（最多 255 字），金额及调整后的余额不能超出数据库整数范围。

通知是当前异常/待办视图：作品审核完成或任务不再失败后，对应通知不再出现。已读记录按管理员和通知状态版本持久化；重复标记幂等，不能标记无权限的来源。运行时告警按当前 API 进程的异常周期生成，恢复后再次异常或进程重启将产生新告警。批量响应的逐项失败覆盖记录不存在情形；数据库事务失败会整单回滚并返回错误。导出超过 10000 行明确拒绝，不静默截断；财务导出窗口为 UTC 最近 1–90 天，金额列单位为分。

## 验证记录

本轮管理端浏览器验收使用真实 Chrome 和类型完整的 API fixtures，覆盖 1440/768/375 三种视口、全部主要列表和详情路由、Drawer、筛选分页、设置脏状态、批量与导出、通知和角色入口，共 88/88 通过；截图、请求形状和汇总报告保存在被忽略的 `.tmp/admin-acceptance/`。数据库集成测试仍需 PostgreSQL 容器健康后执行。

## 验收重点

浏览器验收至少覆盖 `/admin/login`、刷新深链、登录失效回跳、375/768/1440 视口、Drawer 键盘关闭、筛选分页、确认弹窗 loading、批量部分失败、导出失败重试和通知标记已读。使用独立测试账号与测试库，不能用生产管理员进行写操作。
