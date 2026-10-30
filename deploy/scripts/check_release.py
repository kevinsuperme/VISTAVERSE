"""Generate reviewable immutable image locks; never starts or pulls containers."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess

SERVICES = {"api": "printfilm-api", "web": "printfilm-web", "admin-web": "printfilm-admin-web"}
REGISTRY = "gcc-registry.cn-hangzhou.cr.aliyuncs.com/gcc"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def validate_version(version):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", version):
        raise ValueError("invalid release tag")
    if version.lower() in {"latest", "main", "master", "dev", "stable", "edge"} or any(
        word in version.lower() for word in ("replace", "placeholder", "example", "your-", "<", ">")
    ):
        raise ValueError("mutable or placeholder release tag rejected")


def choose_digest(repository, inspection):
    candidates = [value for value in inspection.get("RepoDigests", []) if value.startswith(repository + "@")]
    if len(candidates) != 1 or not DIGEST.fullmatch(candidates[0].split("@", 1)[1]):
        raise ValueError("expected exactly one digest for the selected repository; push/pull the release first")
    return candidates[0]


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def build_metadata(output):
    revision = run("git", "rev-parse", "HEAD")
    if not SHA.fullmatch(revision):
        raise ValueError("invalid git revision")
    dirty = bool(run("git", "status", "--porcelain", "--untracked-files=normal"))
    suffix = "-dirty-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") if dirty else ""
    version = revision + suffix
    write_new(output, f"PRINTFILM_VERSION={version}\nPRINTFILM_GIT_REVISION={revision}\nPRINTFILM_GIT_DIRTY={str(dirty).lower()}\n")
    return version


def create_lock(version, revision, output, record, local=False):
    validate_version(version)
    if not SHA.fullmatch(revision):
        raise ValueError("--revision must be the full 40-character git SHA")
    if "dirty" in version.lower():
        raise ValueError("dirty builds cannot become production releases")
    if output.exists() or record.exists():
        raise ValueError("refusing to overwrite an existing release lock or record")
    images = {}
    overlay = {"services": {}}
    for service, name in SERVICES.items():
        repo = name if local else f"{REGISTRY}/{name}"
        source = f"{repo}:{version}"
        info = json.loads(run("docker", "image", "inspect", source))[0]
        image_id = info.get("Id", "")
        if not DIGEST.fullmatch(image_id):
            raise ValueError("invalid inspected image ID")
        labels = (info.get("Config") or {}).get("Labels") or {}
        # Local builds must prove source metadata. Registry artifacts may come
        # from older CI; their supplied revision remains an operator assertion.
        if local and (labels.get("org.opencontainers.image.revision") != revision or labels.get("cloud.cattoken.source.dirty") != "false"):
            raise ValueError("local image missing matching clean source labels")
        if labels.get("org.opencontainers.image.revision") not in {None, "", revision}:
            raise ValueError("image revision label disagrees with release revision")
        digest = choose_digest(repo, info)
        overlay["services"][service] = {"image": digest, "pull_policy": "always"}
        images[service] = {"source_tag": source, "image_id": image_id, "repo_digest": digest,
                           "image_revision_label": labels.get("org.opencontainers.image.revision")}
    evidence = {"schema": 1, "version": version, "revision": revision, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "images": images}
    # JSON is a YAML subset accepted by Compose; no env, URLs or credentials
    # from image config are copied into these reviewable artifacts.
    write_new(output, json.dumps(overlay, indent=2) + "\n")
    write_new(record, json.dumps(evidence, indent=2) + "\n")


def verify_lock(output, record):
    lock = json.loads(output.read_text(encoding="utf-8"))
    evidence = json.loads(record.read_text(encoding="utf-8"))
    validate_version(evidence["version"])
    if not SHA.fullmatch(evidence["revision"]) or "dirty" in evidence["version"].lower():
        raise ValueError("release revision invalid or dirty")
    if set(lock["services"]) != set(SERVICES) or set(evidence["images"]) != set(SERVICES):
        raise ValueError("release must include all three application services")
    for service in SERVICES:
        item = evidence["images"][service]
        digest = item["repo_digest"]
        source = item["source_tag"]
        if not source.endswith(":" + evidence["version"]) or source.rsplit(":", 1)[0] != digest.split("@", 1)[0]:
            raise ValueError("source tag repository/version does not match locked digest")
        if item.get("image_revision_label") not in {None, "", evidence["revision"]}:
            raise ValueError("recorded image revision label disagrees with release revision")
        if "@" not in digest or not DIGEST.fullmatch(digest.split("@", 1)[1]) or not DIGEST.fullmatch(item["image_id"]):
            raise ValueError("invalid release digest or image ID")
        if lock["services"][service] != {"image": digest, "pull_policy": "always"}:
            raise ValueError("lock does not match release evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-metadata")
    build.add_argument("--output", type=Path, required=True)
    for command in ("lock", "verify"):
        sub = commands.add_parser(command)
        sub.add_argument("--output", type=Path, required=True)
        sub.add_argument("--record", type=Path, required=True)
        if command == "lock":
            sub.add_argument("--version", required=True)
            sub.add_argument("--revision", required=True)
            sub.add_argument("--local", action="store_true", help="inspect pushed local repositories (still requires RepoDigests)")
    args = parser.parse_args()
    try:
        if args.command == "build-metadata":
            print(build_metadata(args.output))
        elif args.command == "lock":
            create_lock(args.version, args.revision, args.output, args.record, args.local)
            verify_lock(args.output, args.record)
            print("Immutable release lock created; deployment has not been executed.")
        else:
            verify_lock(args.output, args.record)
            print("Release lock matches recorded image IDs and repository digests.")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Release check failed: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
