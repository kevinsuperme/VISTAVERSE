"""Read-only bounded Docker probes; publish only numeric metrics, never logs/env."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

SERVICES = ("api", "web", "admin-web", "postgres", "redis")
def command(*args: str, timeout: int = 5) -> str:
    """Keep command errors private; caller emits a zero success gauge."""
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          timeout=timeout).stdout.strip()


def number(value) -> float:
    """Only finite numeric values can enter the metrics output."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite metric")
    return result


def add(metrics: list[str], name: str, value, service: str | None = None) -> None:
    """Render fixed names and allowlisted service labels."""
    label = ""
    if service is not None:
        if service not in SERVICES:
            raise ValueError("unexpected service")
        label = '{service="' + service + '"}'
    metrics.append(f"vistaverse_{name}{label} {number(value):g}")


def latest_report(backup_dir: Path, filename: str, success_key: str) -> float:
    """Trust only explicit successful reports; arbitrary archive mtime is insufficient."""
    latest = 0.0
    # One report per batch; cap candidates and avoid reading media/SQL contents.
    candidates = sorted(backup_dir.glob("*/" + filename), key=lambda p: p.parent.name, reverse=True)[:100]
    for path in candidates:
        if path.stat().st_size > 65536:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get(success_key) is True:
                stamp = number(report.get("completed_at_unix", 0))
                if stamp <= time.time() + 60:
                    latest = max(latest, stamp)
        except (ValueError, OSError):
            continue
    return latest


def collect(project: str, backup_dir: Path) -> tuple[str, bool]:
    """Scrape running containers, Redis persistence and completed backup evidence."""
    metrics: list[str] = []
    success = True
    containers = {}
    try:
        ids = command("docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project}",
                      "--format", "{{.ID}}").split()
        # Inspect JSON in one call; only fixed state/allowlisted Compose labels
        # enter metrics. Config.Env and arbitrary labels never leave memory.
        if ids:
            raw = json.loads(command("docker", "inspect", *ids[:30]))
            for source in raw:
                labels = ((source.get("Config") or {}).get("Labels") or {})
                service = labels.get("com.docker.compose.service")
                state = source.get("State") or {}
                health = ((state.get("Health") or {}).get("Status") or "none")
                item = {"service": service, "running": bool(state.get("Running")),
                        "restarts": source.get("RestartCount", 0),
                        "health": health, "id": source.get("Id")}
                if service in SERVICES:
                    if service in containers:
                        raise ValueError("multiple replicas require explicit aggregation")
                    containers[service] = item
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        success = False
    for service in SERVICES:
        item = containers.get(service, {})
        add(metrics, "container_running", int(bool(item.get("running"))), service)
        add(metrics, "container_healthy", int(item.get("health") in {"healthy", "none"}), service)
        add(metrics, "container_restarts_total", item.get("restarts", 0), service)
        success = success and bool(item)

    try:
        redis_id = containers["redis"]["id"]
        output = command("docker", "exec", redis_id, "sh", "-c",
            'export REDISCLI_AUTH="$REDIS_PASSWORD"; redis-cli --raw INFO memory stats persistence; '
            'redis-cli --raw ZCARD ai_movie:oss:pending:v2; '
            'redis-cli --raw ZCARD ai_movie:oss:failed:v2')
        info = {}
        counts = []
        for line in output.splitlines():
            if ":" in line and not line.startswith("#"):
                key, value = line.split(":", 1)
                info[key] = value.strip()
            elif line.strip().isdigit():
                counts.append(int(line.strip()))
        for name, key in (("redis_used_memory_bytes", "used_memory"),
                          ("redis_maxmemory_bytes", "maxmemory"),
                          ("redis_evicted_keys_total", "evicted_keys"),
                          ("redis_rejected_connections_total", "rejected_connections")):
            add(metrics, name, info[key])
        healthy = (info.get("aof_enabled") == "1" and info.get("aof_last_write_status") == "ok"
                   and info.get("aof_last_bgrewrite_status") == "ok")
        add(metrics, "redis_aof_healthy", int(healthy))
        if len(counts) != 2:
            raise ValueError("missing queue counters")
        add(metrics, "oss_pending", counts[0])
        add(metrics, "oss_quarantined", counts[1])
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        success = False
        add(metrics, "redis_aof_healthy", 0)

    for metric, filename, key in (
        ("backup_timestamp_seconds", "backup-report.json", "backup_complete"),
        ("restore_timestamp_seconds", "restore-report.json", "restore_complete"),
    ):
        try:
            add(metrics, metric, latest_report(backup_dir, filename, key))
        except OSError:
            add(metrics, metric, 0)
            success = False
    add(metrics, "collect_timestamp_seconds", time.time())
    add(metrics, "collect_success", int(success))
    return "\n".join(metrics) + "\n", success


def write_metrics(path: Path, content: str) -> None:
    """Atomic replace avoids partial Prometheus scrapes; no secrets in this file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".vistaverse-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.chmod(0o644)  # node-exporter is unprivileged.
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    """Collect once; scheduling belongs to the supplied systemd timer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.project):
        parser.error("invalid Compose project")
    content, success = collect(args.project, args.backup_dir)
    if args.output:
        write_metrics(args.output, content)
    else:
        print(content, end="")
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
