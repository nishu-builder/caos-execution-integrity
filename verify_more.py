"""Recheck the extra cases from Git objects and the lab's external observations."""
from verify import require
from verify_suite import git, at, read, args_without_salt


def check_result(row, report, repo):
    require(row["request"] in report["requests"].values(), "unretained request")
    require(row["result"] in report["results"], "unretained result")
    require(read(repo,row["result"],"stdout") == row["stdout"], "stdout mismatch")
    require(read(repo,row["result"],"exit") == "0\n", "worker failed")
    require(at(repo,row["result"],"state") == row["state"], "state mismatch")


def check_more(demo, report, repo):
    rows = {r["id"]:r for r in demo["cases"]}
    if demo["id"] == "history":
        require({k:r["verdict"] for k,r in rows.items()} ==
                {"final-only":"CLEAR","retained-history":"ALERT","rewritten-ref":"CLEAR","pinned-tip":"REJECT"},
                "wrong history outcomes")
        write, cleanup = demo["steps"]
        for step in demo["steps"]:
            check_result(step, report, repo)
        require(at(repo,write["request"],"workspace") == demo["initial"], "wrong initial workspace")
        require(at(repo,cleanup["request"],"workspace") == write["state"], "cleanup did not follow write")
        require(cleanup["state"] == demo["initial"], "final snapshot is not restored")
        require(read(repo,write["state"],"publication.canary") == "local effect\n", "missing intermediate effect")
        require(at(repo,demo["start"],"") == at(repo,demo["end"],""), "initial/final trees differ")
        require(git(repo,"rev-parse",demo["during"]+"^") == demo["start"], "first history edge wrong")
        require(git(repo,"rev-parse",demo["end"]+"^") == demo["during"], "cleanup history edge wrong")
        require(at(repo,demo["during"],"") == write["state"], "intermediate history tree wrong")
        require(git(repo,"rev-list","--count",demo["rewritten"]) == "1", "rewritten history not parentless")
        require(at(repo,demo["rewritten"],"") == cleanup["state"], "rewritten tree differs")
        require(rows["pinned-tip"]["pinned_tip"] == demo["end"] and
                rows["pinned-tip"]["offered_tip"] == demo["rewritten"] != demo["end"], "tip substitution absent")
        require(rows["final-only"]["observed_tree"] == cleanup["state"] and
                rows["retained-history"]["observed_tree"] == write["state"], "history view changed")
        require(rows["rewritten-ref"]["offered_tip"] == demo["rewritten"], "wrong rewritten reference")
        require(report["history_tips"]["history_recorded"] == demo["end"] and
                report["history_tips"]["history_rewritten"] == demo["rewritten"], "history retention mismatch")
    elif demo["id"] == "retries":
        expected = {"unsafe-1":("UNKNOWN",1),"unsafe-2":("201",2),"safe-1":("UNKNOWN",1),
                    "safe-2":("200",1),"payload-conflict":("409",1)}
        require(set(rows) == set(expected), "missing retry case")
        for name,row in rows.items():
            require((row["verdict"],row["effect_count"]) == expected[name], "wrong retry outcome")
            require(read(repo,row["result"],"state/status.txt").strip() == row["verdict"], "response status mismatch")
        for mode in ("unsafe","safe"):
            one,two = rows[mode+"-1"],rows[mode+"-2"]
            require(one["request"] != two["request"] and
                    args_without_salt(repo,one["request"]) == args_without_salt(repo,two["request"]),
                    "retry changed more than the attempt salt")
            require(one["key"] == two["key"], "intent key changed on retry")
        effects = demo["service_observations"]["effects"]
        require(len(effects["unsafe"]) == 2 and len(effects["safe"]) == 1, "wrong external effect counts")
        events = demo["service_observations"]["events"]
        require([r["applied"] for r in events] == [True,True,True,False,False], "wrong service effect log")
        require([r["dropped"] for r in events] == [True,False,True,False,False], "reply loss not observed")
        require([r["status"] for r in events] == [201,201,201,200,409], "service status differs")
        require(rows["payload-conflict"]["key"] == rows["safe-1"]["key"], "conflict used another key")
        require(read(repo,rows["payload-conflict"]["request"],"workspace/body.txt") !=
                read(repo,rows["safe-1"]["request"],"workspace/body.txt"), "conflicting payload unchanged")
        for mode in ("unsafe","safe"):
            for effect in effects[mode]:
                require(effect["key"] == rows[mode+"-1"]["key"] and effect["body"] == "publish-demo-artifact",
                        "effect payload or key mismatch")
    elif demo["id"] == "access":
        require({k:r["verdict"] for k,r in rows.items()} ==
                {"broad-input":"CANARY READ","narrow-input":"PUBLIC ONLY","known-hash":"CANARY READ",
                 "gateway-public":"200","gateway-private":"403","gateway-bypass":"CANARY READ"}, "wrong access outcomes")
        canary = git(repo,"cat-file","blob",demo["canary_oid"]) + "\n"
        require(canary == demo["canary"], "canary object mismatch")
        for label in ("broad-input","known-hash","gateway-bypass"):
            require(rows[label]["stdout"] == canary, "canary was not actually read")
        for label in ("narrow-input","known-hash","gateway-bypass"):
            require(at(repo,rows[label]["request"],"workspace") == demo["public_tree"], "input scope changed")
        require("private" not in git(repo,"ls-tree","--name-only",demo["public_tree"]).splitlines(), "private data in public tree")
        require(rows["gateway-private"]["requested_oid"] == demo["canary_oid"], "gateway denied a different object")
        require(read(repo,rows["gateway-private"]["result"],"state/status.txt") == "403\n", "gateway did not deny read")
        require(read(repo,rows["gateway-public"]["result"],"state/status.txt") == "200\n", "public read failed")
        require(read(repo,rows["gateway-private"]["result"],"state/response.txt") == "denied\n", "denied response leaked data")
        require(demo["gateway_observations"]["reads"] ==
                [{"oid":demo["public_oid"],"status":200},{"oid":demo["canary_oid"],"status":403}], "wrong gateway log")
