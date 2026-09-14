#!/usr/bin/env python3
"""Rerun published Caos worker requests using only Python, Git, and a Caos server."""
import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "docs/rerun"


def git(repo, *args, data=None):
    p = subprocess.run(["git", "-C", str(repo), *args], input=data,
                       capture_output=True, timeout=180)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace"))
    return p.stdout


def oid(value):
    if not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("Invalid Git object ID: " + str(value))
    return value


def entries(repo, tree):
    rows = {}
    for row in git(repo, "ls-tree", "-z", oid(tree)).split(b"\0"):
        if row:
            meta, name = row.split(b"\t", 1)
            rows[name.decode()] = meta.decode()
    return rows


def make_tree(repo, rows):
    return oid(git(repo, "mktree", "-z", data=b"".join(
        (meta + "\t" + name).encode() + b"\0"
        for name, meta in sorted(rows.items()))).decode().strip())


def change(repo, tree, name, kind, value):
    rows = entries(repo, tree)
    rows[name] = ("040000" if kind == "tree" else "100644") + " " + kind + " " + oid(value)
    return make_tree(repo, rows)


def blob(repo, value):
    return git(repo, "hash-object", "-w", "--stdin", data=value).decode().strip()


def import_package(package, repo):
    # An exclusive new directory avoids altering any reader's checkout or refs.
    repo.mkdir(parents=True, exist_ok=False)
    git(repo, "init", "--quiet")
    manifest_bytes = (package / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    ref = "refs/heads/caos-rerun"
    git(repo, "fetch", "--quiet", str((package / "requests.bundle").resolve()),
        ref + ":" + ref)
    commit = git(repo, "rev-parse", ref).decode().strip()
    if commit != oid((package / "commit").read_text().strip()):
        raise ValueError("Bundle commit differs from the published commit")
    if git(repo, "show", commit + ":manifest.json") != manifest_bytes:
        raise ValueError("Manifest differs from the bundled manifest")
    git(repo, "fsck", "--full", "--no-reflogs")
    validate(repo, manifest, commit)
    return manifest, commit


def validate(repo, manifest, commit):
    image = oid(manifest["portable_image"])
    image_rows = entries(repo, image)
    if "base" in image_rows:
        raise ValueError("Portable image still depends on an external base")
    original_image = oid(manifest["original_image"])
    old_image = entries(repo, original_image)
    base_image = entries(repo, oid(manifest["imported_base_image"]))
    if "base" in base_image:
        raise ValueError("Imported base is not self-contained")
    expected_layers = [base_image[k] for k in sorted(base_image) if k.startswith("layer")]
    expected_layers += [old_image[k] for k in sorted(old_image) if k.startswith("layer")]
    wanted = {"layer" + str(i).zfill(2): value for i, value in enumerate(expected_layers)}
    wanted["config.json"] = old_image["config.json"]
    if image_rows != wanted:
        raise ValueError("Portable image differs from imported base plus original overlay")
    if git(repo, "rev-parse", commit + ":image").decode().strip() != image:
        raise ValueError("Wrong image in bundle")
    for row in manifest["jobs"]:
        name = row["name"]
        original, portable = oid(row["original_request"]), oid(row["request"])
        if git(repo, "rev-parse", commit + ":requests/" + name).decode().strip() != portable:
            raise ValueError("Wrong bundled request: " + name)
        before, after = entries(repo, original), entries(repo, portable)
        if after.pop("base") != "040000 tree " + image:
            raise ValueError("Request does not use the portable image")
        if before.pop("base") != "040000 tree " + original_image:
            raise ValueError("Original request has an unexpected image")
        if before != after:
            raise ValueError("Portability conversion changed tool or inputs: " + name)
        if row["expected_result"]:
            if git(repo, "cat-file", "-t", oid(row["expected_result"])).strip() != b"tree":
                raise ValueError("Expected result is missing")
    for value in manifest["support_objects"]:
        git(repo, "cat-file", "-e", oid(value))


def run_job(repo, server, row, exact):
    original = oid(row["request"])
    request = original
    if not exact:
        request = change(repo, original, "salt", "blob",
                         blob(repo, ("rerun-" + uuid.uuid4().hex).encode()))
        before, after = entries(repo, original), entries(repo, request)
        before.pop("salt", None)
        after.pop("salt", None)
        if before != after:
            raise ValueError("Fresh request changed more than salt")
    git(repo, "update-ref", "refs/rerun/requests/" + request, request)
    pending = dict(name=row["name"], original_request=row["original_request"],
                   portable_request=original, submitted_request=request,
                   expected_result=row["expected_result"], status="prepared")
    job_file = repo / (request + ".json")
    job_file.write_text(json.dumps(pending, indent=2) + "\n")
    git(repo, "push", "--quiet", server, request + ":refs/caos/req/" + request)
    pending["status"] = "submitted; outcome unknown until a result is received"
    job_file.write_text(json.dumps(pending, indent=2) + "\n")
    # No automatic retries: the response may be lost after work has happened.
    with urlopen(server + "/run?req=" + request, timeout=180) as response:
        kind, result = response.read().decode().strip().split()
    if kind != "tree":
        raise ValueError("Expected a result tree")
    result = oid(result)
    git(repo, "fetch", "--quiet", "--no-tags", server, result)
    git(repo, "update-ref", "refs/rerun/results/" + request, result)
    expected = row["expected_result"]
    match = result == expected
    record = dict(name=row["name"], original_request=row["original_request"],
                  portable_request=original, submitted_request=request,
                  result=result, expected_result=expected, matches=match,
                  mode="exact-portable-request" if exact else "fresh-salt")
    if not match:
        record["diff"] = git(repo, "diff", "--stat", expected, result).decode()
    job_file.write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["list", "verify", "run"])
    p.add_argument("--package", type=Path, default=PACKAGE)
    p.add_argument("--server", help="Your Caos server URL, reachable from this computer")
    p.add_argument("--only", default="all", help="One job name or experiment name; default: all portable jobs")
    p.add_argument("--exact", action="store_true", help="Reuse the portable request unchanged; may hit cache")
    p.add_argument("--workdir", type=Path, help="New directory for imported objects and rerun results")
    args = p.parse_args()
    manifest = json.loads((args.package / "manifest.json").read_text())
    if args.action == "list":
        for row in manifest["jobs"]:
            print(row["name"] + ": " + (row["skip"] or "ready"))
        return
    if args.action == "run":
        if not args.server or urlsplit(args.server).scheme not in ("http", "https"):
            p.error("run requires --server http(s)://YOUR_CAOS_SERVER")
    repo = (args.workdir or ROOT / ".runtime" / ("rerun-" + uuid.uuid4().hex)).resolve()
    manifest, commit = import_package(args.package.resolve(), repo)
    print("Imported and verified complete Git objects: " + str(repo), flush=True)
    if args.action == "verify":
        print("Verified " + str(len(manifest["jobs"])) + " requests; no external image base.")
        return
    selected = [r for r in manifest["jobs"] if args.only in ("all", r["name"], r["experiment"])]
    if not selected:
        p.error("No matching job or experiment")
    ready = [r for r in selected if not r["skip"]]
    for row in selected:
        if row["skip"]:
            print("SKIP " + row["name"] + ": " + row["skip"], flush=True)
    if not ready:
        p.error("These jobs require live fixtures; use demo.py run for the full experiment")
    server = args.server.rstrip("/")
    # Known-hash access jobs intentionally read a fake canary outside their input
    # tree. Upload that explicit support closure too, never the whole report.
    support = manifest["support_objects"] if any(
        r["name"] in ("access-known-hash", "access-gateway-bypass") for r in ready) else []
    for value in support:
        git(repo, "push", "--quiet", server, value + ":refs/caos/req/" + value)
    report = dict(package_commit=commit, mode="exact" if args.exact else "fresh", jobs=[])
    output = repo / "rerun.json"
    for row in ready:
        result = run_job(repo, server, row, args.exact)
        report["jobs"].append(result)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(("MATCH " if result["matches"] else "DIFFERENT ") + row["name"] +
              " " + result["result"], flush=True)
        if not result["matches"]:
            print(result["diff"])
            raise RuntimeError("Result differs; details retained in " + str(output))
    print("All " + str(len(ready)) + " result trees match byte for byte. Record: " + str(output))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print("reproduce: " + str(error), file=sys.stderr)
        sys.exit(1)
