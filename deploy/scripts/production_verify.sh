#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot read-only diagnostics. No env dump, logs, restarts or business writes.
ROOT="${VISTAVERSE_ROOT:-/opt/vistaverse/current}"
PROJECT="${VISTAVERSE_COMPOSE_PROJECT:-vistaverse}"
BACKUPS="${VISTAVERSE_BACKUP_DIR:-/opt/vistaverse/backups}"
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || exit 2
printf 'checked_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
collector_status=0
python3 "$ROOT/deploy/scripts/collect_metrics.py" --project "$PROJECT" --backup-dir "$BACKUPS" || collector_status=$?
df -h / /opt
free -m
set +e
python3 - <<'PY'
import json
import sys
from urllib.request import build_opener, ProxyHandler
failed = False
client = build_opener(ProxyHandler({}))
for path in ("/api/health", "/api/ready"):
    try:
        with client.open("http://127.0.0.1:8000" + path, timeout=4) as response:
            data = json.loads(response.read(1024))
            ok = response.status == 200 and data.get("ok") is True
            print(path, "ok=" + str(ok))
            failed |= not ok
    except Exception as error:
        print(path, "failed=" + type(error).__name__)
        failed = True
sys.exit(1 if failed else 0)
PY
probe_status=$?
set -e
if [[ "$collector_status" -ne 0 || "$probe_status" -ne 0 ]]; then
  exit 1
fi
