#!/usr/bin/env python3
"""Maintainer: assemble the recorded requests with a fully imported base image."""
import argparse
import json
from pathlib import Path
from reproduce import git, entries, make_tree, change, blob, oid

ROOT = Path(__file__).resolve().parent


def pack(base_image, output):
    report = json.loads((ROOT / "docs/gallery/report.json").read_text())
    ref = (ROOT / "docs/gallery/evidence-ref").read_text().strip()
    git(ROOT, "fetch", "--quiet", str(ROOT / "docs/gallery/evidence.bundle"), ref)
    original_image = git(ROOT, "rev-parse", next(iter(report["requests"].values())) + ":base").decode().strip()
    rows = entries(ROOT, base_image)
    if "base" in rows:
        raise ValueError("Import the full base image, without --base")
    # Append the original Caos overlay after every base layer, preserving its
    # config and all file/symlink/mode objects. No registry locator remains.
    old = entries(ROOT, original_image)
    base_layers = sorted(k for k in rows if k.startswith("layer"))
    for name in sorted(k for k in old if k.startswith("layer")):
        rows["layer" + str(len(base_layers)).zfill(2)] = old[name]
        base_layers.append(name)
    rows["config.json"] = old["config.json"]
    image = make_tree(ROOT, rows)
    observed = {}
    for demo in report["demos"]:
        if demo["id"] == "execution":
            raw = demo["raw"]
            records = [raw["wrong_command_control"]] + [c.get("actual") for c in raw["cases"]]
        else:
            records = demo.get("cases", []) + demo.get("steps", [])
        for row in records:
            if row and row.get("request") and row.get("result"):
                observed[row["request"]] = row["result"]
    jobs, requests, originals, results = [], {}, {}, {}
    for name, request in report["requests"].items():
        if git(ROOT, "rev-parse", request + ":base").decode().strip() != original_image:
            raise ValueError("Unexpected second image; package it explicitly")
        portable = change(ROOT, request, "base", "tree", image)
        experiment = "retries" if name.startswith("retry-") else name.split("-")[0]
        expected = observed.get(request)
        skip = ""
        if name.startswith(("replay-live-", "retry-", "access-gateway-public", "access-gateway-private")):
            skip = "Needs the live HTTP fixture and its service state; use demo.py run --only " + experiment
        elif expected is None:
            skip = "Prepared but not executed in the recorded experiment; no observed result to compare"
        jobs.append(dict(name=name, experiment=experiment, original_request=request,
                         request=portable, expected_result=expected, skip=skip))
        requests[name] = "040000 tree " + portable
        originals[name] = "040000 tree " + request
        if expected:
            results[expected] = "040000 tree " + expected
    access = next(d for d in report["demos"] if d["id"] == "access")
    support = [access["canary_oid"]]
    manifest = dict(schema=1, evidence_commit=(ROOT / "docs/gallery/evidence-commit").read_text().strip(),
                    caos_revision=report["caos_revision"], platform="linux/amd64",
                    original_image=original_image, imported_base_image=base_image,
                    portable_image=image, support_objects=support, jobs=jobs,
                    note="Only base changes from recorded requests; the runner adds fresh salt. Worker jobs do not reproduce host policies or live services.")
    payload = (json.dumps(manifest, indent=2) + "\n").encode()
    tree = make_tree(ROOT, {
        "manifest.json": "100644 blob " + blob(ROOT, payload),
        "image": "040000 tree " + image,
        "imported-base": "040000 tree " + base_image,
        "requests": "040000 tree " + make_tree(ROOT, requests),
        "originals": "040000 tree " + make_tree(ROOT, originals),
        "results": "040000 tree " + make_tree(ROOT, results),
        "support": "040000 tree " + make_tree(ROOT, {v: "100644 blob " + v for v in support}),
    })
    commit = git(ROOT, "-c", "user.name=Caos demos", "-c", "user.email=lab@example.invalid",
                 "commit-tree", tree, data=b"Portable Caos requests and complete image layers\n").decode().strip()
    ref = "refs/heads/caos-rerun"
    git(ROOT, "update-ref", ref, commit)
    output.mkdir(parents=True, exist_ok=True)
    git(ROOT, "bundle", "create", str(output / "requests.bundle"), ref)
    (output / "manifest.json").write_bytes(payload)
    (output / "commit").write_text(commit + "\n")
    print(str(sum(not j["skip"] for j in jobs)) + " runnable jobs; " + commit)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-image", required=True, help="caos-cli import-image output for the full original base")
    p.add_argument("--output", type=Path, default=ROOT / "docs/rerun")
    a = p.parse_args()
    pack(oid(a.base_image), a.output.resolve())
