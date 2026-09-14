#!/usr/bin/env python3
"""Import retained evidence into an empty Git repository and verify it offline."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from verify import check as check_execution
from verify_suite import check_suite

ROOT = Path(__file__).resolve().parent


def check_folder(folder, suite):
    report_bytes = (folder / "report.json").read_bytes()
    report = json.loads(report_bytes)
    trust = json.loads((folder / "trust.json").read_text())
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sample-", dir=ROOT / ".runtime") as directory:
        def git(*args):
            return subprocess.run(["git", "-C", directory, *args], check=True,
                                  capture_output=True).stdout
        git("init")
        ref = "refs/heads/evidence/" + ("gallery-" if suite else "") + report["run_id"]
        git("fetch", str(folder / "evidence.bundle"), ref + ":" + ref)
        git("fsck", "--full", "--no-reflogs")
        if git("show", ref + ":report.json") != report_bytes:
            raise ValueError("report differs from the bundled report")
        if suite:
            if git("rev-parse", ref + ":source").decode().strip() != report["source_tree"]:
                raise ValueError("source tree differs from the bundle")
            count = check_suite(report, directory, trust)
        else:
            count = check_execution(report, trust["witness_public_key"], trust["approver_public_key"], directory)
    print(f"{'Suite' if suite else 'Original sample'} verified in an empty repository: {count} cases.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", type=Path, help="Verify one exported suite directory")
    args = p.parse_args()
    if args.suite:
        check_folder(args.suite.resolve(), True)
    else:
        check_folder(ROOT / "docs", False)
        check_folder(ROOT / "docs/gallery", True)
    print("Consistency verified against published keys and retained objects; this is not independent attestation.")


if __name__ == "__main__":
    main()
