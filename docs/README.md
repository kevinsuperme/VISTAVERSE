# 万象影界 | VISTAVERSE 文档中心

这里是万象影界（VISTAVERSE）的产品与工程文档。`PRINTFILM` / `printfilm`
仍是仓库、镜像、环境变量和技术接口使用的内部代号。

| 文档 | 说明 |
|------|------|
| [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md) | **全新项目说明**：品牌、产品模块、业务流程、架构、数据流、运行与测试 |
| [brand-guidelines.md](./brand-guidelines.md) | **品牌规范**：Logo、色彩、宣传语、语气和产品命名 |
| [STANDARDS.md](./STANDARDS.md) | **全局规范**（注释、分层、前后端、Git、发布、安全） |
| [SECURITY.md](./SECURITY.md) | 生产安全基线、媒体边界、密钥与事件排查 |
| [CODEX.md](./CODEX.md) | 项目级 Codex 配置、专属技能、交叉审核与验证命令 |
| [OPERATIONS.md](./OPERATIONS.md) | Compose 启动、迁移、备份、健康检查与升级回滚 |
| [TESTING.md](./TESTING.md) | 后端/前端测试命令、CI 和验证边界 |
| [BILLING.md](./BILLING.md) | 计费与易支付 |
| [EPISODE_RULES.md](./EPISODE_RULES.md) | **漫剧分集主规范**（开幕/拆镜/脚本/资产/Seedance/门禁/后续清单） |
| [SEEDANCE_2_5.md](./SEEDANCE_2_5.md) | Seedance 2.5 公开参数 / 参考素材上限 / 本仓库映射 |
| [SHOT_SPLITTING.md](./SHOT_SPLITTING.md) | 拆分镜头操作指南（Fragment / Beat、空镜 vs 口播） |
| [PLACEHOLDER_BACKLOG.md](./PLACEHOLDER_BACKLOG.md) | **占位 / 待开发功能总表**（ComingSoon、禁用入口、建议优先级） |
| [PRINTFILM_UI_ROADMAP.md](./PRINTFILM_UI_ROADMAP.md) | UI 还原对照：路由、已接线能力、视觉约定 |
| [PRINTFILM_UI_DESIGN_PROMPTS.md](./PRINTFILM_UI_DESIGN_PROMPTS.md) | 多产品平台 UI 生图提示词（壳 / 工作台 / 漫剧 / 科普 / 工具） |
| [../deploy/README.md](../deploy/README.md) | 中间件 compose / 本地运维补充 |
| [../README.md](../README.md) | 仓库总览与本地启动 |

相关项目级工具配置：

- [../.codex/config.toml](../.codex/config.toml) — 仓库级 Codex 默认值与可选文档 MCP
- [../.agents/skills/vistaverse-operations/SKILL.md](../.agents/skills/vistaverse-operations/SKILL.md) — Docker、服务器和回滚操作规范
- [../.agents/skills/vistaverse-review/SKILL.md](../.agents/skills/vistaverse-review/SKILL.md) — 多角色交叉审核规范

本机 `.env`、`.tmp/`、`docs/releases/` 和包含凭据的发布脚本属于运行态或受保护资产，不进入开源仓库。

**维护约定**：

- 编码与协作先读 [STANDARDS.md](./STANDARDS.md)；约定变更时同步更新该文。
- 新增 `ComingSoon` / `disabled` 功能入口时，同步更新 `PLACEHOLDER_BACKLOG.md`；功能上线后勾掉对应条目。
- 现网发版记录写在本机 `docs/releases/`（不上开源仓库）。
