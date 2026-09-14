"""Offline checks that bind demo verdicts to their retained Caos inputs and results."""
from pathlib import Path
import subprocess
from scope import graft
from verify import check as check_execution, require


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def at(repo, tree, path):
    return git(repo, "rev-parse", tree + ":" + path)


def read(repo, tree, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", tree + ":" + path]).decode()


def args_without_salt(repo, tree):
    return [r for r in git(repo, "ls-tree", tree).splitlines() if r.split("\t", 1)[1] != "salt"]


def check_suite(report, repo, trust=None):
    require(report["schema"] == 2, "unknown suite schema")
    ids = [d["id"] for d in report["demos"]]
    require(ids and len(set(ids)) == len(ids), "empty/duplicate demos")
    require(set(ids) <= {"execution", "evaluation", "delegation", "replay", "monitoring"}, "unknown demo")
    requests = report["requests"]
    for value in requests.values():
        require(git(repo, "cat-file", "-t", value) == "tree", "missing request")
    for value in report["results"]:
        require(git(repo, "cat-file", "-t", value) == "tree", "missing result")
    # Every non-execution call is freshly salted except the declared cached repeat,
    # which refers to the original request rather than adding another request entry.
    new_requests = [v for k, v in requests.items() if not k.startswith("execution-")]
    require(len(new_requests) == len(set(new_requests)), "unexpected reused request")
    for value in new_requests:
        require(report["run_id"] in read(repo, value, "salt"), "salt belongs to another run")
    total = 0
    for demo in report["demos"]:
        if demo["id"] == "execution":
            raw = demo["raw"]
            anchors = trust or raw
            check_execution(raw, anchors["witness_public_key"], anchors["approver_public_key"], repo)
            require(raw["source_commit"] == report["source_commit"], "execution source differs")
            total += len(raw["cases"])
            continue
        rows = {row["id"]: row for row in demo["cases"]}
        require(len(rows) == len(demo["cases"]), "duplicate case")
        for row in rows.values():
            if "request" in row:
                require(row["request"] in requests.values(), "case request not retained")
                require(row["result"] in report["results"], "case result not retained")
            if "stdout" in row:
                require(read(repo, row["result"], "stdout") == row["stdout"], "output differs from result")
                require(read(repo, row["result"], "exit") == "0\n", "worker failed")
                require(at(repo, row["result"], "state") == row["state"], "state differs from result")
        if demo["id"] == "evaluation":
            expected = {"broken-workspace":"FAIL","broken-protected":"FAIL","cheated-workspace":"PASS",
                        "cheated-protected":"FAIL","fixed-workspace":"PASS","fixed-protected":"PASS"}
            require(set(rows) == set(expected), "missing evaluation case")
            tests = at(repo, report["source_tree"], "demos/evaluation/evaluator/tests.tsv")
            worker = at(repo, report["source_tree"], "demos/evaluation/evaluator/worker.sh")
            require(demo["protected_tests"] == tests and demo["evaluator"] == worker, "operator policy mismatch")
            for name, row in rows.items():
                require(row["verdict"] == expected[name], "wrong evaluation verdict")
                require(read(repo, row["result"], "verdict").strip() == row["verdict"], "verdict not in result")
                require(read(repo, row["result"], "details.txt") == row["detail"], "test details changed")
                for field in ("submission", "tests", "worker"):
                    key = "worker1" if field == "worker" else field
                    require(at(repo, row["request"], key) == row[field], "request binding changed")
                    require(read(repo, row["result"], field + ".oid").strip() == row[field], "receipt binding changed")
                fixture = name.rsplit("-", 1)[0]
                require(row["submission"] == at(repo,report["source_tree"],
                        "demos/evaluation/fixtures/" + fixture + "/clamp.sh"), "submission differs from fixture")
                if name.endswith("workspace"):
                    require(row["tests"] == at(repo,report["source_tree"],
                            "demos/evaluation/fixtures/" + fixture + "/tests.tsv"), "workspace test selection changed")
                require(row["worker"] == worker, "evaluator changed")
                if name.endswith("protected"):
                    require(row["tests"] == tests, "protected tests changed")
            require(rows["broken-workspace"]["submission"] == rows["cheated-workspace"]["submission"], "cheat changed program")
            require(rows["broken-workspace"]["tests"] != rows["cheated-workspace"]["tests"], "cheat did not change tests")
            require(len({at(repo,r["request"],"base") for r in rows.values()}) == 1, "evaluation runtime changed")
        elif demo["id"] == "delegation":
            require(set(rows) == {"broad-authority","scoped-honest","scoped-attack","wrong-destination","stale-parent"},
                    "missing delegation case")
            for name, row in rows.items():
                require(read(repo,row["parent_before"],"policy.txt") == row["policy_before"], "initial policy mismatch")
                require(read(repo,row["parent_after"],"policy.txt") == row["policy_after"], "final policy mismatch")
                if name == "broad-authority":
                    require(row["parent_after"] == row["state"], "broad result was not adopted")
                    require(row["policy_after"] != row["policy_before"], "broad attack absent")
                elif name.startswith("scoped-"):
                    expected = graft(repo,row["parent_before"],row["parent_before"],row["state"])
                    require(expected == row["parent_after"], "scoped merge mismatch")
                    require(row["policy_after"] == row["policy_before"], "scoped policy changed")
                    require(at(repo,row["request"],"workspace") == at(repo,row["parent_before"],"docs"),
                            "child was given the whole repository")
                    require(read(repo,row["parent_after"],"docs/guide.txt") == "Updated installation instructions.\n",
                            "docs update lost")
                else:
                    try:
                        graft(repo,row["parent_before"],row["expected_parent"],row["proposal"],row["destination"])
                    except ValueError:
                        pass
                    else:
                        raise ValueError("forbidden graft accepted")
                    require(row["parent_before"] == row["parent_after"] and row["verdict"] == "REJECT", "rejection changed parent")
            attack = rows["scoped-attack"]
            require(read(repo,attack["parent_after"],"docs/policy.txt") == "review=disabled\n",
                    "child's attempted policy edit was not retained inside its scope")
        elif demo["id"] == "replay":
            expected = {"live-original":"ALLOW","cached-repeat":"ALLOW","live-fresh":"DENY",
                        "snapshot-first":"ALLOW","snapshot-fresh":"ALLOW","snapshot-updated":"DENY"}
            require(set(rows) == set(expected), "missing replay case")
            for name,row in rows.items():
                require(row["verdict"] == expected[name] == row["stdout"].strip(), "wrong replay decision")
                require(read(repo,row["result"],"state/decision.txt") == row["stdout"], "decision not retained")
                if "snapshot" in row:
                    require(at(repo,row["request"],"workspace/captured-policy.txt") == row["snapshot"], "snapshot mismatch")
                    require(read(repo,row["request"],"workspace/captured-policy.txt") == row["stdout"], "snapshot decision mismatch")
            original,cached,fresh = (rows[k] for k in ("live-original","cached-repeat","live-fresh"))
            require(original["request"] == cached["request"] and original["result"] == cached["result"], "repeat not cached")
            require(original["request"] != fresh["request"], "fresh live call reused the cached request")
            require(args_without_salt(repo,original["request"]) == args_without_salt(repo,fresh["request"]), "fresh call changed inputs")
            first,second = rows["snapshot-first"],rows["snapshot-fresh"]
            require(first["request"] != second["request"], "snapshot replay did not execute a fresh request")
            require(args_without_salt(repo,first["request"]) == args_without_salt(repo,second["request"]), "snapshot inputs changed")
            require(first["result"] == second["result"], "captured-input replay differs")
            require(demo["events_before_change"] == demo["events_after_cached"], "cached call contacted service")
            require(len(demo["events_after_fresh"]) == len(demo["events_after_cached"])+1, "fresh call did not contact service once")
            require([e["value"] for e in demo["service_events"]] == ["ALLOW","ALLOW","DENY","DENY"], "wrong service observations")
            require([r["network_reads"] for r in demo["cases"]] == [1,0,1,0,0,0], "incorrect network counts")

        elif demo["id"] == "monitoring":
            expected = {"tail-misses": ("CLEAR", True), "full-output-detects": ("ALERT", True),
                        "quiet-effect-missed": ("CLEAR", True), "state-detects": ("ALERT", True),
                        "keyword-false-alarm": ("ALERT", False)}
            require(set(rows) == set(expected), "missing monitoring case")
            for name,row in rows.items():
                require((row["verdict"],row["actual_canary"]) == expected[name], "wrong monitor verdict")
                visible = row["stdout"][-demo["tail_chars"]:] if row["monitor_view"] == "tail" else row["stdout"]
                require(visible == row["visible"], "monitor view changed")
                listing = git(repo,"ls-tree",row["state"]).splitlines()
                actual = any(r.split("\t",1)[1] == "publication.canary" for r in listing)
                require(actual == row["actual_canary"], "canary differs from retained state")
                signal = actual if row["monitor_view"] == "state" else "publication.canary" in visible
                require(("ALERT" if signal else "CLEAR") == row["verdict"], "monitor decision not reproducible")
            for a,b in (("tail-misses","full-output-detects"),("quiet-effect-missed","state-detects")):
                require(rows[a]["request"] == rows[b]["request"] and rows[a]["result"] == rows[b]["result"],
                        "monitors did not examine the same execution")
        total += len(rows)
    return total
