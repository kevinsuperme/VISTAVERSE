# VISTAVERSE 生产监控与备份恢复验收

本文是可执行的验收 runbook。监控脚本默认只读；备份脚本只在指定新目录生成备份，恢复脚本只有显式 `--run` 才在隔离目标创建临时资源。它们不会重启生产容器、修改生产配置或写入生产业务库。除非有单独授权，脚本输出不能作为已经完成生产验收的证据。

## 1. 发布前记录

```bash
cd /opt/vistaverse/current
docker compose -p vistaverse --env-file deploy/.env.docker -f docker-compose.full.yml config --quiet
docker compose -p vistaverse --env-file deploy/.env.docker -f docker-compose.full.yml images
docker compose -p vistaverse --env-file deploy/.env.docker -f docker-compose.full.yml ps -a
```

保存 API、Web、Admin 三个应用镜像的 `RepoDigests`/Image ID、当前发布目录、上一回滚目录、迁移版本和备份批次。不要把 `config` 展开结果或环境文件复制到工单。

## 2. 生产监控

| 检查 | 目标 | 失败条件 | 建议告警 |
| --- | --- | --- | --- |
| Liveness | `/api/health` | 非 200 或超过 4 秒 | 连续 2 次 |
| Readiness | `/api/ready` | 非 200 或超过 4 秒 | 连续 2 次并摘除流量 |
| 任务运行时 | 管理员 `/api/health/details` | `task_runtime.healthy=false`、连续失败或心跳过期 | 5 分钟 |
| 请求质量 | 同一诊断响应 | 错误/慢请求或平均延迟持续上升 | 按业务基线 |
| Redis | `INFO memory stats persistence` | 接近 512 MiB、`evicted_keys` 非 0、AOF 非正常 | 立即 |
| 容器/主机 | inspect、`df -h`、`free -m`、`docker stats` | 非 running、重启增加、媒体盘 < 20% | 立即/15 分钟 |

```bash
sudo bash /opt/vistaverse/current/deploy/scripts/production_verify.sh
```

只采集固定字段和计数。禁止采集 Authorization、API Key、签名 URL 查询串、邮箱和完整异常堆栈。脚本失败应记录为“检查失败”，不能改写成“服务异常已确认”。

仓库提供可选的本机监控 overlay：`docker-compose.monitoring.yml`、Prometheus、Blackbox、node-exporter 及 systemd textfile collector。启用前应将 `deploy/monitoring/public-targets.json` 换成实际 HTTPS 域名，把 Prometheus 端口限制在管理网段，并让两个路径变量一致：

```bash
sudo install -d -m 0755 -o root -g root /var/lib/vistaverse-monitoring
sudo cp deploy/monitoring/vistaverse-metrics.service /etc/systemd/system/
sudo cp deploy/monitoring/vistaverse-metrics.timer /etc/systemd/system/
sudo install -m 0600 deploy/monitoring/env.example /etc/vistaverse-monitoring.env
# 编辑 env：COMPOSE_PROJECT=vistaverse、BACKUP_DIR=...、TEXTFILE_DIR=/var/lib/vistaverse-monitoring
MONITOR_TEXTFILE_DIR=/var/lib/vistaverse-monitoring docker compose -f docker-compose.yml -f docker-compose.monitoring.yml config --quiet
sudo systemctl daemon-reload && sudo systemctl enable --now vistaverse-metrics.timer
```

上述命令只准备监控；实际启用前须审查 systemd 权限、Prometheus 存储和外部探针出口。本次目标服务器尚未安装这些服务或对应 timer。

## 3. 备份批次

数据库和媒体必须使用同一批次标识；备份期间不要执行迁移、清理或重启。

```bash
sudo bash /opt/vistaverse/current/deploy/scripts/backup_manifest.sh \
  --output-dir /opt/vistaverse/backups/$(date -u +%Y%m%dT%H%M%SZ)
```

脚本生成受控目录中的 `pg_dump`、媒体卷归档、SHA-256 清单和元数据。备份应加密、异机保存并限制读取权限。Redis AOF 不能替代 PostgreSQL 或媒体备份。

## 4. 隔离恢复演练

恢复必须使用临时 Compose 项目、临时 PostgreSQL 数据库和临时媒体卷，端口仅绑定 `127.0.0.1`，并设置 `TASK_RUNTIME_ENABLED=false`、`BILLING_ENABLED=false`、`OSS_ENABLED=false`、`ARK_MOCK=true`。先做校验和，再导入备份：

```bash
sudo bash /opt/vistaverse/current/deploy/scripts/verify_backup_restore.sh \
  --backup-dir /opt/vistaverse/backups/<批次目录> \
  --compose-project printfilm-restore-<批次>
```

该命令默认只做 SHA-256 校验。真正导入需要变更单和隔离 Compose 目标：

```bash
sudo bash /opt/vistaverse/current/deploy/scripts/verify_backup_restore.sh \
  --backup-dir /opt/vistaverse/backups/<批次目录> \
  --compose-project printfilm-restore-<批次> --run
```

验收记录应包括恢复耗时、RPO/RTO、`schema_migrations` 最大版本 2、关键表行数、外键错误、媒体数量/字节数/抽样哈希、认证后的只读业务查询和审核人。不得把目标 URL 指向生产库或生产媒体卷。

## 5. 本轮证据边界

本次改动已完成本地代码、静态编译和定向测试；未在目标服务器执行发布、重启、备份生成或隔离恢复。服务器验收必须补齐脚本输出、镜像摘要和恢复报告。
