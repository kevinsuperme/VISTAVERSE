#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BACKUP=""; PROJECT=""; RUN=0; IMAGE="postgres:16.4-alpine"
HELPER="$(cd -- "$(dirname -- "$0")" && pwd)/backup_archive.py"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir) BACKUP="${2:?missing backup directory}"; shift 2;;
    --compose-project) PROJECT="${2:?missing project}"; shift 2;;
    --postgres-image) IMAGE="${2:?missing image}"; shift 2;;
    --run) RUN=1; shift;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done
[[ "$BACKUP" = /* && -d "$BACKUP" && ! -L "$BACKUP" ]] || { echo 'absolute backup directory required' >&2; exit 2; }
[[ "$PROJECT" =~ ^printfilm-restore-[a-z0-9][a-z0-9-]{0,39}$ ]] || { echo 'project must use printfilm-restore-* prefix' >&2; exit 2; }
python3 "$HELPER" verify "$BACKUP" >/dev/null
if [[ "$RUN" != 1 ]]; then echo 'archive_verification=passed; restore_not_executed'; exit 0; fi
TOKEN="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
NAME="$PROJECT-$TOKEN"; VOLUME="$NAME-pgdata"; CID=""; OWNED_VOLUME=""
EVIDENCE="$(mktemp -d "${TMPDIR:-/tmp}/printfilm-restore-evidence.XXXXXXXX")"
printf 'evidence_dir=%s\n' "$EVIDENCE"
cleanup() {
  local status=$?
  local cleanup_failed=0
  if [[ -n "$CID" ]] && [[ "$(docker inspect -f '{{index .Config.Labels "vistaverse.restore.owner"}}' "$CID" 2>/dev/null)" = "$TOKEN" ]]; then
    docker logs "$CID" > "$EVIDENCE/postgres.log" 2>&1 || true
    docker rm -f "$CID" > "$EVIDENCE/container-cleanup.log" 2>&1 || cleanup_failed=1
  fi
  if [[ -n "$OWNED_VOLUME" ]] && [[ "$(docker volume inspect -f '{{index .Labels "vistaverse.restore.owner"}}' "$OWNED_VOLUME" 2>/dev/null)" = "$TOKEN" ]]; then
    docker volume rm "$OWNED_VOLUME" > "$EVIDENCE/volume-cleanup.log" 2>&1 || cleanup_failed=1
  fi
  [[ "$cleanup_failed" = 0 ]] || status=1
  [[ $status = 0 ]] || printf 'restore_verification=failed; evidence=%s\n' "$EVIDENCE" >&2
  return "$status"
}
# Collision checks happen before trap registration; never adopt existing objects.
if docker container inspect "$NAME" >/dev/null 2>&1 || docker volume inspect "$VOLUME" >/dev/null 2>&1; then echo 'restore target already exists' >&2; exit 1; fi
docker image inspect "$IMAGE" >/dev/null # require local image, never pull
trap cleanup EXIT
OWNED_VOLUME="$(docker volume create --label "vistaverse.restore.owner=$TOKEN" "$VOLUME")"
[[ "$OWNED_VOLUME" = "$VOLUME" ]] || { OWNED_VOLUME=""; exit 1; }
PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
CID="$(docker create --name "$NAME" --label "vistaverse.restore.owner=$TOKEN" --network none --pull never -e "POSTGRES_PASSWORD=$PASSWORD" -e POSTGRES_DB=printfilm -v "$VOLUME:/var/lib/postgresql/data" "$IMAGE")"
[[ "$CID" =~ ^[a-f0-9]{64}$ ]] || { CID=""; exit 1; }
docker start "$CID" >/dev/null
for _ in $(seq 1 60); do docker exec "$CID" pg_isready -U postgres -d printfilm >/dev/null 2>&1 && break; sleep 1; done
docker exec "$CID" pg_isready -U postgres -d printfilm >/dev/null
docker exec -i "$CID" pg_restore -U postgres -d printfilm --no-owner --no-privileges --exit-on-error < "$BACKUP/postgres.dump" > "$EVIDENCE/restore.log" 2>&1
version="$(docker exec "$CID" psql -v ON_ERROR_STOP=1 -U postgres -d printfilm -Atqc 'SELECT COALESCE(MAX(version),0) FROM schema_migrations')"
[[ "$version" = 2 ]] || { echo "unexpected schema version: $version" >&2; exit 1; }
for table in users projects task_runs schema_migrations; do
  count="$(docker exec "$CID" psql -v ON_ERROR_STOP=1 -U postgres -d printfilm -Atqc "SELECT count(*) FROM $table")"
  [[ "$count" =~ ^[0-9]+$ ]] || exit 1
  printf '%s=%s\n' "$table" "$count" | tee -a "$EVIDENCE/restored-counts.txt"
done
# Media was streamed and checked by hash, without extracting untrusted paths.
cleanup
trap - EXIT
python3 "$HELPER" restore-report "$BACKUP" "$EVIDENCE"
printf 'restore_verification=passed; schema=2; evidence=%s\n' "$EVIDENCE"
