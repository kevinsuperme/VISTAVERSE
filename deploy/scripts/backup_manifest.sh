#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PROJECT="${VISTAVERSE_COMPOSE_PROJECT:-vistaverse}"
HELPER="$(cd -- "$(dirname -- "$0")" && pwd)/backup_archive.py"
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUT="${2:?missing output directory}"; shift 2;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done
[[ "$OUT" = /* && "$OUT" != / ]] || { echo 'absolute new --output-dir required' >&2; exit 2; }
mkdir -- "$OUT" # Reject existing directories and links; preserve failed batches.
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || { echo 'invalid Compose project' >&2; exit 2; }
# Identify the actual running release by labels. Backup must not depend on
# build.env or interpolate a possibly newer Compose configuration.
API="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=api' --format '{{.ID}}')"
PG="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=postgres' --format '{{.ID}}')"
[[ -n "$API" && "$API" != *$'\n'* && -n "$PG" && "$PG" != *$'\n'* ]] || { echo 'one running API and postgres required' >&2; exit 1; }
# Inspection never persists raw environment/credentials.
docker inspect "$API" "$PG" | python3 -c '
import json,sys,datetime
from pathlib import Path
items=json.load(sys.stdin)
mounts=[m for m in items[0]["Mounts"] if m["Destination"]=="/app/static/generated"]
if len(mounts)!=1 or mounts[0]["Type"]!="volume": raise SystemExit("API media volume mount not found")
data={"created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"media_volume":mounts[0]["Name"],"containers":[{"id":i["Id"],"image_id":i["Image"],"image":i["Config"]["Image"]} for i in items]}
Path(sys.argv[1]).write_text(json.dumps(data,indent=2)+"\n")
' "$OUT/metadata.json"
docker exec "$PG" pg_dump --version > "$OUT/pg-dump-version.txt"
docker exec "$PG" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$OUT/postgres.dump"
[[ -s "$OUT/postgres.dump" ]]
docker exec -i "$API" python - source /app/static/generated < "$HELPER" > "$OUT/media-files.json"
docker exec "$API" tar -czf - -C /app/static/generated . > "$OUT/media.tar.gz"
gzip -t "$OUT/media.tar.gz"
python3 "$HELPER" build "$OUT"
(cd "$OUT" && sha256sum manifest.json postgres.dump media.tar.gz metadata.json media-files.json pg-dump-version.txt > SHA256SUMS)
python3 "$HELPER" backup-report "$OUT"
printf 'backup_complete=%s\n' "$OUT"
