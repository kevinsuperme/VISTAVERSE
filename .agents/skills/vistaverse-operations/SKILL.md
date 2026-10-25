---
name: vistaverse-operations
description: Run, validate, release, troubleshoot, and safely operate the VISTAVERSE (PRINTFILM) FastAPI, React/Vite, PostgreSQL, Redis, FFmpeg, and Docker Compose stack.
---

Use this skill when a task concerns VISTAVERSE local Docker debugging, server deployment, release checks, service
start/stop, logs, health checks, rollback, backups, or operational failure diagnosis.

## Repository facts

- Root full-stack entry points: `docker-compose.yml` (published images) and `docker-compose.full.yml` (local builds).
- Production-style middleware-only entry point: `deploy/docker-compose.yml`; API can run from `backend` on the host.
- API health: `GET /api/health`; authenticated details: `GET /api/health/details`.
- Persistent data: Compose volumes `printfilm_pgdata`, `printfilm_redisdata`, and `printfilm_media`.
- API is intentionally one Uvicorn worker because the task scheduler, poller, watchdog, and executor run in-process.
- Required runtime pieces: Python 3.12, Node.js 22, Docker Engine/Compose, PostgreSQL 16, Redis 7, FFmpeg, and a Chinese font for subtitle burn-in.

## Safe workflow

1. Record `git status --short`, the Docker context, Compose project name, env-file path, ports, volumes, and target services.
2. Inspect `README.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`, `deploy/README.md`, and the relevant `.env.*.example`.
3. Run `docker compose ... config --quiet` before build or start. Never print resolved secrets.
4. Use a unique project name for isolated local middleware (`printfilm-local-middleware`) and keep database/Redis ports on
   `127.0.0.1` (`15432`/`16379`). Do not reuse another project's volumes.
5. Start with the existing entry point. For full stack use:
   `docker compose --env-file deploy/.env.docker -f docker-compose.full.yml up -d --build`.
   For middleware plus host API use `deploy/docker-compose.yml` and run `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` from `backend`.
6. Validate `docker compose ps -a`, health status, bounded logs, `/api/health`, and one relevant authenticated/API path.
7. Stop with project-scoped `docker compose ... down` when requested; preserve volumes by default. `down -v`, volume deletion,
   global prune, and production rollback require an explicit scope and a backup/restore plan.

## Release and rollback

- Pin one `PRINTFILM_VERSION` for API, web, and admin images.
- Back up PostgreSQL and the media volume before upgrades. Record the previous image tag and migration state.
- Roll back by restoring the previous image tag and restarting the project; never remove data volumes as part of a normal rollback.
- Keep `SECRET_KEY`, database/Redis passwords, provider keys, OSS keys, and SMTP credentials in ignored env/secret stores only.

## Failure routing

- `config` errors: check Compose file order, project directory, env-file and missing variable names.
- Build/pull errors: capture the first failing step and separate network, registry, dependency, architecture, and disk causes.
- Unhealthy API: inspect exit code, healthcheck output, database/Redis dependency health, startup migration logs, and FFmpeg/font availability.
- Running but inaccessible API: check bind address, published port, reverse proxy `/api` routing, CORS, and service DNS.
- Queue stalls: inspect scheduler/poller heartbeats, lock waits, orphan recovery, and `TASK_RUNTIME_*`; increasing workers is not a substitute for diagnosing locks.

For detailed commands and server boundaries, read `references/runbook.md`.
