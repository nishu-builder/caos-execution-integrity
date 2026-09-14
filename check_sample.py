#!/usr/bin/env python3
"""Verify the published sample using the trust anchors shipped in this checkout."""
import json
from pathlib import Path
import subprocess
import tempfile
from verify import check

ROOT = Path(__file__).resolve().parent


def main():
    report = json.loads((ROOT / "docs/report.json").read_text())
    trust = json.loads((ROOT / "docs/trust.json").read_text())
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sample-", dir=ROOT / ".runtime") as directory:
        def git(*args):
            subprocess.run(["git", "-C", directory, *args], check=True, capture_output=True)
        git("init")
        ref = "refs/heads/evidence/" + report["run_id"]
        git("fetch", str(ROOT / "docs/evidence.bundle"), ref + ":" + ref)
        git("fsck", "--full", "--no-reflogs")
        count = check(report, trust["witness_public_key"], trust["approver_public_key"], directory)
    print(f"Sample verified in an empty repository: {count} Caos cases, 3 process cases, 6 permission probes.")
    print("Trust comes from this checkout's published keys; this is not independent attestation.")


if __name__ == "__main__":
    main()
