#!/usr/bin/env python3
"""Check an exported run against explicitly pinned keys and retained Git objects."""
import argparse
import json
from pathlib import Path
import subprocess
from crypto import verify, verify_receipt

EXPECTED = {
    "honest": (True, False), "mutable-workspace": (True, True),
    "hashes-only": (True, True), "direct-bypass-unrestricted": (False, True),
    "direct-bypass-restricted": (False, False), "substitute": (False, None),
    "approval-forgery": (False, None), "result-swap": (False, False),
    "key-swap": (False, False), "inline-output": (True, False),
    "receipt-replay": (False, None), "authorization-reuse": (False, None),
    "custom-tool": (True, False), "pinned-workspace": (True, False),
    "compromised-signer": (True, True),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def blob(repo, tree, path):
    rows = git(repo, "ls-tree", tree, "--", path).decode().splitlines()
    if not rows:
        return None
    return git(repo, "show", tree + ":" + path)


def check(report, witness_key, approver_key, repo):
    require(report["witness_public_key"] == witness_key, "witness trust anchor mismatch")
    require(report["approver_public_key"] == approver_key, "approver trust anchor mismatch")
    os_rows = report["os_experiment"]
    require([r["name"] for r in os_rows] == ["honest", "same-uid-hijack", "separate-uid"],
            "missing process experiment")
    require(all(r["transcript"] == os_rows[0]["transcript"] for r in os_rows),
            "transcripts differ")
    for row, effects in zip(os_rows, [(True, False), (False, True), (True, False)]):
        signed = verify(witness_key, row["signed_transcript"])
        require(signed == dict(type="transcript", **row["transcript"]), "transcript mismatch")
        require((row["audit_ran"], row["publication_canary"]) == effects, "wrong process effects")
    probes = os_rows[2]["setup"]["probes"]
    require(len(probes) == 6 and all(p["blocked"] for p in probes.values()), "permission probe failed")
    cases = {r["name"]: r for r in report["cases"]}
    require(len(report["cases"]) == len(EXPECTED) and set(cases) == set(EXPECTED), "missing/duplicate cases")
    actual_requests = []
    for name, row in cases.items():
        require((row["accepted"], row.get("actual_canary")) == EXPECTED[name], name + ": wrong outcome")
        if "approval" in row:
            approved = verify(approver_key, row["approval"])
            require(approved["type"] == "approval" and approved["schema"] == 1 and
                    approved["run_id"] == report["run_id"], name + ": wrong approval")
        if "receipt" in row:
            try:
                verify_receipt(witness_key, row["receipt"], approved)
                accepted = True
            except ValueError:
                accepted = False
            require(accepted == row["accepted"], name + ": incorrect verifier verdict")
        actual = row.get("actual")
        if actual:
            actual_requests.append(actual["request"])
            canary = blob(repo, actual["result"], "state/publication.canary") is not None
            require(canary == row["actual_canary"], name + ": result contradicts observed canary")
            require(blob(repo, actual["result"], "stdout").decode() == row["actual_stdout"],
                    name + ": stdout mismatch")
            require(blob(repo, actual["result"], "exit") == b"0\n", name + ": worker failed")
        if row.get("displayed_result"):
            result = row["displayed_result"]
            require(blob(repo, result, "stdout").decode() == row["displayed_stdout"],
                    name + ": displayed output is not in result")
            require((blob(repo, result, "state/publication.canary") is not None) == row["displayed_canary"],
                    name + ": displayed state mismatch")
    require(len(actual_requests) == len(set(actual_requests)), "effect-producing cases reused requests")
    requests = report["requests"]
    require(len(requests.values()) == len(set(requests.values())), "request identities not unique")
    salts = []
    for name, request in requests.items():
        require(git(repo, "cat-file", "-t", request).strip() == b"tree", "request is not a tree")
        salt = blob(repo, request, "salt")
        require(salt and report["run_id"].encode() in salt, "request salt not bound to this run")
        salts.append(salt)
    require(len(salts) == len(set(salts)), "request salts reused")
    pinned = blob(repo, requests["audit-pinned-workspace"], "workspace/tools/audit.sh")
    mutated = blob(repo, requests["mutated"], "workspace/tools/audit.sh")
    require(pinned != mutated, "mutable workspace control did not change tool bytes")
    require(blob(repo, requests["audit-pinned-workspace"], "command") ==
            blob(repo, requests["mutated"], "command"), "mutable control changed command text")
    journal = report["witness_journal"]
    require(len({r["call_id"] for r in journal}) == len(journal), "authorization dispatched twice")
    for name in ("substitute", "approval-forgery", "receipt-replay", "direct-bypass-restricted"):
        require(not any(r["call_id"] == name for r in journal), name + ": unexpected dispatch")
    require(cases["direct-bypass-restricted"]["proxy_response"]["transport_errno"] == 1,
            "direct route was not blocked by kernel")
    require(cases["compromised-signer"]["actual"]["request"] !=
            cases["compromised-signer"]["approval"]["body"]["request"], "signer fault absent")
    require(cases["compromised-signer"]["displayed_canary"] is False, "signer did not hide effect")
    return len(cases)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report")
    p.add_argument("--repo", default=".", help="Git repository containing the evidence objects")
    p.add_argument("--witness-key", required=True, help="Public key pinned through a trusted channel")
    p.add_argument("--approver-key", required=True, help="Public key pinned through a trusted channel")
    a = p.parse_args()
    report = json.loads(Path(a.report).read_text())
    count = check(report, a.witness_key, a.approver_key, a.repo)
    print(f"Verified 3 process cases, 6 permission probes, {count} Caos cases, signatures and retained objects.")
    print("This checks consistency with the pinned witness, not honesty of that witness or unobserved side effects.")


if __name__ == "__main__":
    main()
