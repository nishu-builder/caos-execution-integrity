#!/usr/bin/env python3
"""Prepare real caos requests, run the isolated lab, and preserve its evidence."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
CLI = os.environ.get("CAOS_CLI", "caos-cli")
CAOS_REV = "5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3"


def command(*args, input=None, timeout=180):
    result = subprocess.run(args, input=input, cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}:\n{result.stderr}")
    return result.stdout.strip()


def git(*args, input=None):
    return command("git", *args, input=input)


def cli(*args):
    return command(CLI, *args)


def oid(value):
    if not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError(f"Invalid object ID {value!r}")
    return value


def tree(entries):
    return oid(git("mktree", input="".join(
        f"{mode} {kind} {value}\t{name}\n" for name, mode, kind, value in entries)))


def export_evidence(report, requests, output):
    results = {report["wrong_command_control"]["result"]}
    for case in report["cases"]:
        for value in (case.get("displayed_result"), (case.get("actual") or {}).get("result"),
                      case.get("receipt", {}).get("body", {}).get("result")):
            if value:
                results.add(oid(value))
    git("-c", "core.alternateRefsCommand=true", "fetch", "--no-tags", "caos",
        *sorted(set(requests.values()) | results))
    # Never fetch arbitrary remote refs; every object here belongs to this experiment.
    request_tree = tree([(name, "040000", "tree", value) for name, value in requests.items()])
    result_tree = tree([(value, "040000", "tree", value) for value in sorted(results)])
    report_text = json.dumps(report, indent=2) + "\n"
    report_oid = git("hash-object", "-w", "--stdin", input=report_text)
    root = tree([
        ("report.json", "100644", "blob", report_oid),
        ("requests", "040000", "tree", request_tree),
        ("results", "040000", "tree", result_tree),
        ("source", "040000", "tree", git("rev-parse", "HEAD^{tree}")),
    ])
    commit = git("-c", "user.name=Caos integrity lab", "-c", "user.email=lab@example.invalid",
                 "commit-tree", root, input="Execution-integrity experiment " + report["run_id"] + "\n")
    ref = "refs/heads/evidence/" + report["run_id"]
    git("update-ref", ref, commit)
    bundle = output / "evidence.bundle"
    git("bundle", "create", str(bundle), ref)
    git("bundle", "verify", str(bundle))
    (output / "evidence-ref").write_text(ref + "\n")
    (output / "evidence-commit").write_text(commit + "\n")
    (output / "report.json").write_text(report_text)
    return ref


def run_execution(args):
    if git("status", "--porcelain"):
        raise RuntimeError("Commit source changes before running so the evidence names the tested code.")
    image = command("docker", "image", "inspect", args.image, "--format", "{{.Id}}")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / "runs" / run_id
    output.mkdir(parents=True)
    source = git("rev-parse", "HEAD")
    print("Preparing content-pinned caos requests...", flush=True)
    _, base = cli("eval-path", "worker").split()
    requests = {}
    commands = [("audit", "bash tools/audit.sh"), ("publish", "bash tools/publish.sh"),
                ("custom", "bash tools/custom.sh")]
    labels = ("hashes-only", "direct-bypass-unrestricted", "direct-bypass-restricted",
              "substitute", "approval-forgery", "result-swap", "key-swap",
              "inline-output", "pinned-workspace", "compromised-signer")
    commands += [("audit-" + label, "bash tools/audit.sh") for label in labels]
    commands += [("publish-" + label, "bash tools/publish.sh") for label in
                 ("hashes-only", "direct-bypass-unrestricted", "direct-bypass-restricted", "compromised-signer")]
    for name, command_text in commands:
        requests[name] = oid(cli("prepare-request", f"--base:hash={base}",
                                  "--workspace:@=fixture", f"--command={command_text}",
                                  f"--salt={run_id}-{name}"))
    # Actually change a tracked tool after approval. The old request must still
    # execute the old bytes. Also retain the newly formed request as a control.
    audit_path = ROOT / "fixture/tools/audit.sh"
    original = audit_path.read_bytes()
    audit_path.write_bytes((ROOT / "fixture/tools/publish.sh").read_bytes())
    try:
        requests["mutated"] = oid(cli("prepare-request", f"--base:hash={base}",
                                       "--workspace:@=fixture", "--command=bash tools/audit.sh",
                                       f"--salt={run_id}-mutated"))
        inputs = dict(run_id=run_id, server=args.server.rstrip("/"), **requests)
        name = "caos-integrity-" + run_id.lower()
        docker = ["docker", "run", "--name", name, "--rm", "-i",
                  "--cpus=1", "--memory=512m", "--pids-limit=64", "--read-only",
                  "--cap-drop=ALL", "--cap-add=SETUID", "--cap-add=SETGID",
                  "--cap-add=CHOWN", "--cap-add=KILL", "--cap-add=DAC_OVERRIDE",
                  "--security-opt=no-new-privileges",
                  "--tmpfs=/tmp:rw,nosuid,nodev,size=64m",
                  "--network", args.network,
                  "--mount", f"type=bind,src={ROOT},dst=/app,readonly",
                  image, "suite"]
        print("Running process takeover, permission probes, and guarded dispatch...", flush=True)
        try:
            raw = command(*docker, input=json.dumps(inputs), timeout=240)
            report = json.loads(raw)
        finally:
            # Only our uniquely named container; covers timeout and interrupted runs.
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
    finally:
        audit_path.write_bytes(original)
    report.update(source_commit=source, caos_revision=CAOS_REV,
                  lab_image_id=image, requests=requests,
                  workspace_modified_after_approval=True)
    ref = export_evidence(report, requests, output)
    render(report, output / "index.html")
    (ROOT / "runs/latest").write_text(run_id + "\n")
    inspect_report(report)
    print(f"\nEvidence: {ref}\nReport: {output / 'index.html'}\nBundle: {output / 'evidence.bundle'}")


def inspect_report(report):
    print("\nLive process experiment")
    for row in report["os_experiment"]:
        print(f"  {row['name']:<28} stdout={row['transcript']['stdout'].strip()!r} "
              f"audit_ran={row['audit_ran']} publication={row['publication_canary']}")
    print("\nCaos boundary experiments")
    for row in report["cases"]:
        state = "ACCEPT" if row["accepted"] else "REJECT"
        actual = row.get("actual_canary")
        suffix = "" if actual is None else f" canary={actual}"
        print(f"  {row['name']:<30} {state}{suffix}")
    print("\nACCEPT is a verifier verdict, not a claim that the action was safe.")
    print("The hashes-only and compromised-signer cases deliberately demonstrate failures.")


def render(report, target):
    template = (ROOT / "report.html").read_text()
    payload = json.dumps(report).replace("<", "\\u003c")
    target.write_text(template.replace("/*DATA*/null", payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("run")
    p.add_argument("--image", default="caos-execution-integrity:local")
    p.add_argument("--only", choices=("all", "execution", "evaluation", "delegation", "replay"), default="all")
    p.add_argument("--feed-port", type=int, default=18081, help="Loopback port for the temporary replay policy service")
    p.add_argument("--network", required=True, help="Docker network that can reach the caos server")
    p.add_argument("--server", required=True, help="caos URL reachable from that network")
    p = sub.add_parser("inspect")
    p.add_argument("report", nargs="?")
    p = sub.add_parser("render")
    p.add_argument("report")
    p.add_argument("output")
    args = parser.parse_args()
    if args.action == "run":
        from suite import run
        run(args)
    else:
        path = args.report
        if not path:
            latest = ROOT / "runs/latest-gallery"
            if not latest.exists():
                latest = ROOT / "runs/latest"
            run_id = latest.read_text().strip()
            path = ROOT / "runs" / run_id / "report.json"
        report = json.loads(Path(path).read_text())
        if report.get("schema") == 2:
            import suite
            if args.action == "inspect":
                suite.inspect(report)
            else:
                suite.render(report, Path(args.output))
            return
        if args.action == "inspect":
            inspect_report(report)
        else:
            render(report, Path(args.output))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"demo: {e}", file=sys.stderr)
        sys.exit(1)
