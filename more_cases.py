"""Additional real-job cases: disappearing evidence, retries, and read access."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import time

import demo as core
from suite import ROOT, at, text_at, put_blob, replace, get


@contextmanager
def service(run, label, config):
    folder = ROOT / ".runtime" / (label + "-" + run.run_id)
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps(config))
    name = "caos-" + label + "-" + run.run_id.lower()
    image = core.command("docker", "image", "inspect", run.args.image, "--format", "{{.Id}}")
    endpoint = "http://127.0.0.1:" + str(run.args.feed_port)
    try:
        core.command("docker", "run", "-d", "--rm", "--name", name, "--cpus=0.25", "--memory=64m",
                     "--pids-limit=16", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                     "--network", run.args.network, "-p", "127.0.0.1:" + str(run.args.feed_port) + ":8080",
                     "--mount", "type=bind,src=" + str(ROOT) + ",dst=/app,readonly",
                     "--mount", "type=bind,src=" + str(folder) + ",dst=/data,readonly",
                     "--entrypoint", "python3", image, "/app/demo_service.py")
        for _ in range(50):
            try:
                get(endpoint + "/events")
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("local fixture did not start")
        yield name, endpoint, image
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def client_tree(run, tree):
    return replace(tree, "client.sh", "blob", at(run.source, "demos/http-client.sh"))


def commit(tree, parent=None, message="fixture state"):
    parents = ["-p", parent] if parent else []
    return core.git("-c", "user.name=Caos history fixture", "-c", "user.email=lab@example.invalid",
                    "commit-tree", tree, *parents, input=message + "\n")


def history(run):
    print("History: retaining a write that disappears from the final snapshot...", flush=True)
    initial = at(run.source, "demos/history/workspace")
    write = run.shell("history-write", initial, "printf 'local effect\\n' > publication.canary; printf 'OK\\n'")
    cleanup = run.shell("history-cleanup", write["state"], "rm publication.canary; printf 'OK\\n'")
    if cleanup["state"] != initial:
        raise RuntimeError("cleanup did not restore the original tree")
    start = commit(initial, message="before")
    during = commit(write["state"], start, "canary created")
    end = commit(cleanup["state"], during, "canary removed")
    rewritten = commit(cleanup["state"], message="clean history offered instead")
    ref = "refs/demo/history/" + run.run_id
    core.git("update-ref", ref, end)
    pinned = core.git("rev-parse", ref)
    core.git("update-ref", ref, rewritten, end)
    offered = core.git("rev-parse", ref)
    # The evidence commit retains these as parents so a standalone bundle carries
    # both histories. Its ancestry is storage, not an assertion about execution.
    run.history_tips.update(history_recorded=end, history_rewritten=rewritten)
    core.git("update-ref", "-d", ref)
    rows = [
        dict(id="final-only", label="Inspect only the final snapshot", verdict="CLEAR", observed_tree=cleanup["state"]),
        dict(id="retained-history", label="Inspect the retained intermediate snapshot", verdict="ALERT", observed_tree=write["state"]),
        dict(id="rewritten-ref", label="Follow a rewritten branch name", verdict="CLEAR", offered_tip=offered),
        dict(id="pinned-tip", label="Compare that offer with the pinned history tip", verdict="REJECT", pinned_tip=pinned, offered_tip=offered),
    ]
    return dict(id="history", title="A clean final state can hide an earlier action", cases=rows,
                steps=[write, cleanup], initial=initial, start=start, during=during, end=end, rewritten=rewritten)


def retries(run):
    print("Retries: losing a reply after a real local effect has happened...", flush=True)
    workspace = client_tree(run, at(run.source, "demos/retries/workspace"))
    workspace = replace(workspace, "body.txt", "blob", put_blob("publish-demo-artifact"))
    rows = []
    with service(run, "retry", {}) as (name, endpoint, image):
        for mode in ("unsafe", "safe"):
            key = run.run_id + "-" + mode
            for attempt in (1, 2):
                result = run.shell("retry-" + mode + "-" + str(attempt), workspace,
                                   "bash client.sh " + name + " POST /" + mode + " " + key)
                status = text_at(result["result"], "state/status.txt").strip()
                events = json.loads(get(endpoint + "/events"))
                rows.append(dict(id=mode + "-" + str(attempt), label=mode.title() + " attempt " + str(attempt),
                                 verdict=status, effect_count=len(events["effects"][mode]), key=key, mode=mode, **result))
        changed = replace(workspace, "body.txt", "blob", put_blob("publish-another-artifact"))
        key = run.run_id + "-safe"
        conflict = run.shell("retry-conflict", changed, "bash client.sh " + name + " POST /safe " + key)
        events = json.loads(get(endpoint + "/events"))
        rows.append(dict(id="payload-conflict", label="Reuse the key with a different payload",
                         verdict=text_at(conflict["result"], "state/status.txt").strip(),
                         effect_count=len(events["effects"]["safe"]), key=key, mode="safe", **conflict))
        if [(r["verdict"], r["effect_count"]) for r in rows] != [("UNKNOWN",1),("201",2),("UNKNOWN",1),("200",1),("409",1)]:
            raise RuntimeError("retry fixture did not produce the intended outcomes")
    return dict(id="retries", title="A lost reply does not mean the action failed", cases=rows,
                service_observations=events, lab_image_id=image)


def access(run):
    print("Read access: trying a known object outside a child's input tree...", flush=True)
    full = at(run.source, "demos/access/workspace")
    public = at(full, "public")
    secret = at(full, "private/canary.txt")
    guide = at(public, "guide.txt")
    fake = text_at(full, "private/canary.txt")
    broad = run.shell("access-broad", full, "cat private/canary.txt")
    narrow = run.shell("access-narrow", public, "cat guide.txt")
    direct_command = "caos get-hash " + secret + " /cas/retrieved; caos get /cas/retrieved; cat /cas/retrieved"
    direct = run.shell("access-known-hash", public, direct_command)
    if direct["stdout"] != fake:
        raise RuntimeError("known-hash read did not retrieve the toy canary")
    rows = [
        dict(id="broad-input", label="Read the full input tree", verdict="CANARY READ", **broad),
        dict(id="narrow-input", label="Read the supplied public subtree", verdict="PUBLIC ONLY", **narrow),
        dict(id="known-hash", label="Fetch a known hash outside that subtree", verdict="CANARY READ", **direct),
    ]
    gateway_tree = client_tree(run, public)
    with service(run, "access", {"allowed": {guide: text_at(public, "guide.txt")}}) as (name, endpoint, image):
        for label, oid, verdict in (("gateway-public",guide,"200"),("gateway-private",secret,"403")):
            result = run.shell("access-" + label, gateway_tree, "bash client.sh " + name + " GET /blob/" + oid + " unused")
            status = text_at(result["result"], "state/status.txt").strip()
            if status != verdict:
                raise RuntimeError("unexpected object-gateway decision")
            rows.append(dict(id=label, label="Gateway " + ("permits public object" if status=="200" else "denies private object"),
                             verdict=status, requested_oid=oid, **result))
        bypass = run.shell("access-gateway-bypass", public, direct_command)
        rows.append(dict(id="gateway-bypass", label="Bypass the gateway and contact Caos directly", verdict="CANARY READ", **bypass))
        observations = json.loads(get(endpoint + "/events"))
    return dict(id="access", title="A narrow input tree is not a read permission", cases=rows,
                canary_oid=secret, canary=fake, public_tree=public, public_oid=guide,
                gateway_observations=observations, lab_image_id=image)
