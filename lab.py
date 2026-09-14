#!/usr/bin/env python3
"""Isolated Linux process experiment and a signed dispatcher for real caos jobs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from sandbox import no_network_sockets
from crypto import Ed25519PrivateKey, canonical, private_bytes, public_hex, sign, verify, verify_receipt

APP = str(Path(__file__).resolve())
UID = 10001
MAX_PACKET = 1_000_000


def write(path, value, mode=0o600):
    path = Path(path)
    path.write_bytes(value if isinstance(value, bytes) else canonical(value))
    path.chmod(mode)


def drop():
    os.setgroups([])
    os.setgid(UID)
    os.setuid(UID)


def spawn(role, config, unprivileged=False, network_blocked=False):
    def restrict():
        if unprivileged:
            drop()
        if network_blocked:
            no_network_sockets()

    p = subprocess.Popen([sys.executable, APP, role, str(config)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True,
                         preexec_fn=restrict, close_fds=True)
    ready, _, _ = select.select([p.stdout], [], [], 10)
    if not ready or p.stdout.readline().strip() != "READY":
        p.kill()
        _, error = p.communicate(timeout=5)
        raise RuntimeError(f"{role} did not start: {error}")
    return p


def stop(p):
    if p.poll() is None:
        # Only the recorded child process, including a deliberately stopped broker.
        p.kill()
    p.communicate(timeout=5)


def rpc(path, packet):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(90)
        s.connect(str(path))
        s.sendall(canonical(packet) + b"\n")
        data = s.makefile("rb").readline(MAX_PACKET + 1)
        if len(data) > MAX_PACKET or not data.endswith(b"\n"):
            raise ValueError("oversized or incomplete RPC")
        return json.loads(data)


def serve(path, handler, mode=0o600):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(str(path))
        os.chmod(path, mode)
        s.listen(8)
        print("READY", flush=True)
        while True:
            connection, _ = s.accept()
            with connection:
                connection.settimeout(90)
                line = connection.makefile("rb").readline(MAX_PACKET + 1)
                try:
                    if len(line) > MAX_PACKET or not line.endswith(b"\n"):
                        raise ValueError("oversized or incomplete RPC")
                    response = handler(json.loads(line))
                except Exception as e:
                    response = {"transport_error": type(e).__name__ + ": " + str(e), "transport_errno": getattr(e, "errno", None)}
                connection.sendall(canonical(response) + b"\n")


def broker(config):
    if config.get("impersonate"):
        # Controlled post-compromise capability: our own sibling PID and socket only.
        os.kill(config["victim_pid"], signal.SIGSTOP)
        Path(config["socket"]).unlink()

    def handle(packet):
        if config.get("dispatcher"):
            original = copy.deepcopy(packet)
            mode = config["mode"]
            if mode in ("hashes-only", "direct-bypass"):
                if mode == "direct-bypass":
                    # Probe the actual socket syscall before DNS can obscure EPERM.
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
                        pass
                actual = resolve(config["server"], config["alternate"])
                return {"claimed_request": packet["approval"]["body"]["request"],
                        "result": config["alternate_result"],
                        "fixture_observation": {"request": config["alternate"], "result": actual}}
            if mode == "replay":
                return config["old_receipt"]
            if mode == "substitute":
                packet["candidate"] = config["alternate"]
            if mode == "approval-forgery":
                packet["candidate"] = config["alternate"]
                packet["approval"]["body"]["request"] = config["alternate"]
            response = rpc(config["dispatcher"], packet)
            if mode == "result-swap" and "body" in response:
                response["body"]["result"] = config["alternate_result"]
            if mode == "key-swap":
                fake = Ed25519PrivateKey.generate()
                body = dict(original["approval"]["body"], type="resolution",
                            status="resolved", result=config["alternate_result"])
                response = sign(fake, body)
                response["offered_public_key"] = public_hex(fake)
            if mode == "inline-output":
                response["stdout"] = "FORGED INLINE OUTPUT\n"
            return response
        command = config.get("replacement", packet["command"]) if config.get("impersonate") else packet["command"]
        result = subprocess.run(["/bin/sh", "-c", command], cwd=config["work"],
                                capture_output=True, text=True, timeout=3,
                                preexec_fn=drop if os.getuid() == 0 else None,
                                env={"PATH": "/usr/local/bin:/usr/bin:/bin"})
        return {"stdout": result.stdout, "stderr": result.stderr, "exit": result.returncode}
    serve(config["socket"], handle, 0o600)


def probe(config):
    results = {}
    attempts = {
        "stop_handler": lambda: os.kill(config["victim_pid"], signal.SIGSTOP),
        "replace_socket": lambda: Path(config["socket"]).unlink(),
        "rewrite_handler_config": lambda: Path(config["handler_config"]).write_text("{}"),
        "read_signing_key": lambda: Path(config["key"]).read_bytes(),
        "open_handler_memory": lambda: open(f'/proc/{config["victim_pid"]}/mem', "rb").close(),
        "connect_control_socket": lambda: rpc(config["socket"], {"command": "printf bypass"}),
    }
    for name, action in attempts.items():
        try:
            action()
            results[name] = {"blocked": False}
        except PermissionError as e:
            results[name] = {"blocked": True, "errno": e.errno}
    print(json.dumps(results))


def raw_object(server, oid):
    if not re.fullmatch("[0-9a-f]{40}", oid):
        raise ValueError("malformed object ID")
    with urllib.request.urlopen(server + "/object/" + oid, timeout=15) as r:
        raw = r.read(2_000_000)
    if hashlib.sha1(raw).hexdigest() != oid:
        raise ValueError("object bytes do not match their ID")
    header, body = raw.split(b"\0", 1)
    kind, size = header.decode().split()
    if len(body) != int(size):
        raise ValueError("object size mismatch")
    return kind, body


def tree_entries(server, oid):
    kind, body = raw_object(server, oid)
    if kind != "tree":
        raise ValueError("expected tree")
    entries = {}
    while body:
        header, rest = body.split(b"\0", 1)
        mode, name = header.decode().split(" ", 1)
        entries[name] = rest[:20].hex()
        body = rest[20:]
    return entries


def leaf(server, tree, path):
    current = tree
    for part in path.split("/"):
        entries = tree_entries(server, current)
        if part not in entries:
            return None
        current = entries[part]
    return raw_object(server, current)[1].decode()


def resolve(server, request):
    with urllib.request.urlopen(server + "/run?req=" + request, timeout=90) as r:
        kind, result = r.read().decode().strip().split()
    if kind != "tree" or not re.fullmatch("[0-9a-f]{40}", result):
        raise ValueError("invalid caos result")
    return result


def dispatcher(config):
    key = Ed25519PrivateKey.from_private_bytes(Path(config["key"]).read_bytes())
    seen = set()

    def handle(packet):
        approved = packet["approval"]["body"]
        body = {k: approved.get(k) for k in ("run_id", "call_id", "request")}
        body.update(schema=1, type="resolution", status="rejected")
        try:
            approved = verify(config["approver"], packet["approval"])
            if approved.get("schema") != 1 or approved.get("type") != "approval":
                raise ValueError("wrong approval type")
            if approved["run_id"] != config["run_id"]:
                raise ValueError("approval belongs to another run")
            if not re.fullmatch("[0-9a-f]{40}", approved["request"]):
                raise ValueError("malformed approved request")
            if packet["candidate"] != approved["request"]:
                raise ValueError("candidate differs from approved request")
            occurrence = (approved["run_id"], approved["call_id"])
            if occurrence in seen:
                raise ValueError("authorization already consumed")
            # Consume before resolving: failure cannot accidentally authorize a retry.
            seen.add(occurrence)
        except (ValueError, KeyError, TypeError) as e:
            body["reason"] = str(e)
            return sign(key, body)
        actual = config.get("fault_actual_request", approved["request"])
        actual_result = resolve(config["server"], actual)
        with open(config["journal"], "a") as f:
            f.write(json.dumps({"call_id": approved["call_id"], "request": actual,
                                "result": actual_result}) + "\n")
        # Deliberate trusted-component compromise; never selected by a broker packet.
        reported = config.get("fault_reported_result", actual_result)
        body.update(status="resolved", result=reported)
        return sign(key, body)
    serve(config["socket"], handle, 0o666)


def os_experiment(root, key):
    records = []
    original = "printf 'audit ran\\n' > audit.marker; printf 'OK\\n'"
    replacement = "printf 'unauthorized publication\\n' > publication.canary; printf 'OK\\n'"
    for mode in ("honest", "same-uid-hijack", "separate-uid"):
        case = root / mode
        case.mkdir(mode=0o755)
        work = case / "work"
        work.mkdir(mode=0o755)
        os.chown(work, UID, UID)
        control = case / "control"
        control.mkdir(mode=0o755)
        if mode != "separate-uid":
            os.chown(control, UID, UID)
        config = dict(socket=str(control / "exec.sock"), work=str(work))
        cfg = case / "handler.json"
        write(cfg, config, 0o644)
        if mode != "separate-uid":
            os.chown(cfg, UID, UID)
        handler = spawn("broker", cfg, unprivileged=mode != "separate-uid")
        attacker = None
        setup = {"capability_granted": "same Unix UID as handler" if mode != "separate-uid" else "worker UID only",
                 "handler_pid": handler.pid, "worker_uid": UID,
                 "handler_uid": UID if mode != "separate-uid" else 0}
        try:
            if mode == "same-uid-hijack":
                attack_cfg = case / "attack.json"
                write(attack_cfg, dict(config, impersonate=True, victim_pid=handler.pid,
                                       replacement=replacement), 0o644)
                attacker = spawn("broker", attack_cfg, unprivileged=True)
                setup.update(stopped_handler=True, replaced_socket=True, impersonator_pid=attacker.pid)
            elif mode == "separate-uid":
                private = control / "signing.key"
                write(private, private_bytes(key))
                probe_cfg = case / "probe.json"
                write(probe_cfg, dict(config, victim_pid=handler.pid, key=str(private),
                                      handler_config=str(cfg)), 0o644)
                p = subprocess.run([sys.executable, APP, "probe", str(probe_cfg)],
                                   preexec_fn=drop, capture_output=True, text=True, timeout=5)
                if p.returncode:
                    raise RuntimeError(p.stderr)
                setup["probes"] = json.loads(p.stdout)
                if not all(v["blocked"] for v in setup["probes"].values()):
                    raise RuntimeError("OS protection probe unexpectedly succeeded")
            answer = rpc(config["socket"], {"command": original})
            if "transport_error" in answer:
                raise RuntimeError(answer["transport_error"])
            transcript = dict(command=original, **answer)
            records.append({"name": mode, "setup": setup, "transcript": transcript,
                            "signed_transcript": sign(key, dict(type="transcript", **transcript)),
                            "audit_ran": (work / "audit.marker").exists(),
                            "publication_canary": (work / "publication.canary").exists()})
        finally:
            if attacker:
                stop(attacker)
            stop(handler)
    if not (records[0]["transcript"] == records[1]["transcript"] == records[2]["transcript"]):
        raise RuntimeError("The visible transcripts should be byte-identical")
    if records[1]["audit_ran"] or not records[1]["publication_canary"]:
        raise RuntimeError("The impersonator did not replace execution")
    if not records[2]["audit_ran"] or records[2]["publication_canary"]:
        raise RuntimeError("Protected handler ran the wrong command")
    return records


def suite(inputs):
    if os.getuid() != 0:
        raise RuntimeError("Run the lab in its dedicated container; root is required for UID separation")
    os.umask(0o022)
    root = Path("/tmp/integrity-lab")
    root.mkdir(mode=0o755)
    approver = Ed25519PrivateKey.generate()
    witness = Ed25519PrivateKey.generate()
    public = public_hex(witness)
    os_records = os_experiment(root, witness)
    control = root / "dispatcher"
    control.mkdir(mode=0o755)
    key_path = control / "receipt.key"
    write(key_path, private_bytes(witness))
    journal = control / "observed.jsonl"
    write(journal, b"")
    config = dict(socket=str(control / "exec.sock"), key=str(key_path),
                  approver=public_hex(approver), run_id=inputs["run_id"],
                  server=inputs["server"], journal=str(journal))
    cfg = control / "config.json"
    write(cfg, config)
    witness_process = spawn("dispatcher", cfg)
    records = []

    def approval(label, request):
        return sign(approver, dict(schema=1, type="approval", run_id=inputs["run_id"],
                                   call_id=label, request=request))

    def through_broker(label, mode, auth, network_blocked=True, **extra):
        directory = root / ("proxy-" + label)
        directory.mkdir(mode=0o755)
        os.chown(directory, UID, UID)
        proxy_cfg = directory / "config.json"
        write(proxy_cfg, dict(socket=str(directory / "exec.sock"), dispatcher=config["socket"],
                               mode=mode, **extra), 0o644)
        p = spawn("broker", proxy_cfg, unprivileged=True, network_blocked=network_blocked)
        try:
            return rpc(directory / "exec.sock",
                       {"approval": auth, "candidate": auth["body"]["request"]})
        finally:
            stop(p)

    def record(label, auth, envelope, expected, extra=None):
        accepted = False
        error = None
        try:
            verified = verify_receipt(public, envelope, auth["body"])
            accepted = True
        except ValueError as e:
            error = str(e)
        if accepted != expected:
            raise RuntimeError(f"{label}: expected accepted={expected}, got {accepted}: {error}")
        seen = [json.loads(line) for line in journal.read_text().splitlines()]
        own = [r for r in seen if r["call_id"] == auth["body"]["call_id"]]
        actual = own[-1] if own else None
        displayed_result = envelope.get("body", {}).get("result") if accepted else None
        item = dict(name=label, approval=auth, receipt=envelope, accepted=accepted, rejection=error,
                    actual=actual, displayed_result=displayed_result)
        if actual:
            item["actual_canary"] = leaf(inputs["server"], actual["result"], "state/publication.canary") is not None
            item["actual_stdout"] = leaf(inputs["server"], actual["result"], "stdout")
        if displayed_result:
            item["displayed_stdout"] = leaf(inputs["server"], displayed_result, "stdout")
            item["displayed_canary"] = leaf(inputs["server"], displayed_result, "state/publication.canary") is not None
        if extra:
            item.update(extra)
        records.append(item)
        return item

    try:
        auth = approval("honest", inputs["audit"])
        first = through_broker("honest", "honest", auth)
        honest = record("honest", auth, first, True)
        honest_result = first["body"]["result"]
        # Establish a real wrong-command result: both output bytes and effects are inspected.
        wrong_result = resolve(inputs["server"], inputs["publish"])
        if leaf(inputs["server"], wrong_result, "stdout") != honest["actual_stdout"]:
            raise RuntimeError("Wrong command must produce identical stdout")
        if leaf(inputs["server"], wrong_result, "state/publication.canary") is None:
            raise RuntimeError("Wrong command must write the canary")

        mutated_result = resolve(inputs["server"], inputs["mutated"])
        if leaf(inputs["server"], mutated_result, "state/publication.canary") is None:
            raise RuntimeError("Mutable-workspace control did not change behavior")
        records.append(dict(name="mutable-workspace", accepted=True,
                            actual={"request": inputs["mutated"], "result": mutated_result},
                            actual_stdout=leaf(inputs["server"], mutated_result, "stdout"),
                            actual_canary=True, displayed_stdout=honest["actual_stdout"],
                            explanation="The command text stayed the same; its on-disk script changed after approval."))

        # The unprivileged proxy really resolves the wrong request through caos,
        # then returns the honest result ID. Its fixture observation is for this
        # controlled experiment, not evidence a hostile proxy would volunteer.
        naive_auth = approval("hashes-only", inputs["audit-hashes-only"])
        naive = through_broker("hashes-only", "hashes-only", naive_auth, network_blocked=False,
                               server=inputs["server"], alternate=inputs["publish-hashes-only"],
                               alternate_result=honest_result)
        wrong_actual = naive["fixture_observation"]
        records.append(dict(name="hashes-only", approval=naive_auth, accepted=True,
                            actual=wrong_actual, actual_stdout=leaf(inputs["server"], wrong_actual["result"], "stdout"),
                            actual_canary=True, displayed_stdout=honest["actual_stdout"],
                            displayed_result=naive["result"], displayed_canary=False,
                            explanation="Proxy executed another request and returned the approved ID plus an unrelated genuine result."))

        for restricted in (False, True):
            label = "direct-bypass-restricted" if restricted else "direct-bypass-unrestricted"
            auth = approval(label, inputs["audit-" + label])
            response = through_broker(label, "direct-bypass", auth, network_blocked=restricted,
                                       server=inputs["server"], alternate=inputs["publish-" + label],
                                       alternate_result=honest_result)
            extra = {"network_filter": restricted, "proxy_response": response}
            if not restricted:
                actual = response["fixture_observation"]
                extra.update(actual=actual, actual_canary=True,
                             actual_stdout=leaf(inputs["server"], actual["result"], "stdout"))
            else:
                if response.get("transport_errno") != 1:
                    raise RuntimeError("Filtered direct bypass did not fail at the network boundary")
                extra["actual_canary"] = False
            record(label, auth, response, False, extra)

        for mode in ("substitute", "approval-forgery", "result-swap", "key-swap", "inline-output"):
            auth = approval(mode, inputs["audit-" + mode])
            envelope = through_broker(mode, mode, auth, alternate=inputs["publish"],
                                      alternate_result=wrong_result)
            record(mode, auth, envelope, mode == "inline-output")
        auth = approval("receipt-replay", inputs["audit"])
        envelope = through_broker("receipt-replay", "replay", auth, old_receipt=first)
        record("receipt-replay", auth, envelope, False)

        repeated = rpc(config["socket"], {"approval": records[0]["approval"], "candidate": inputs["audit"]})
        # Distinct assertion: a valid authorization cannot cause a second resolution here.
        try:
            verify_receipt(public, repeated, records[0]["approval"]["body"])
            raise RuntimeError("Reused authorization was accepted")
        except ValueError as e:
            records.append(dict(name="authorization-reuse", approval=records[0]["approval"],
                                receipt=repeated, accepted=False, rejection=str(e),
                                explanation="In-memory one-use ledger; no restart durability claim."))

        for label, request in (("custom-tool", inputs["custom"]), ("pinned-workspace", inputs["audit-pinned-workspace"])):
            auth = approval(label, request)
            record(label, auth, through_broker(label, "honest", auth), True)
    finally:
        stop(witness_process)

    # Fault injection deliberately compromises the trusted signer, not an untrusted API flag.
    Path(config["socket"]).unlink()
    compromised_cfg = dict(config, fault_actual_request=inputs["publish-compromised-signer"],
                           fault_reported_result=honest_result)
    write(cfg, compromised_cfg)
    compromised = spawn("dispatcher", cfg)
    try:
        auth = approval("compromised-signer", inputs["audit-compromised-signer"])
        envelope = through_broker("compromised-signer", "honest", auth)
        item = record("compromised-signer", auth, envelope, True,
                      {"explanation": "Signer deliberately lies about both dispatched request and returned result."})
        if not item["actual_canary"] or item["displayed_canary"]:
            raise RuntimeError("Compromised signer counterexample did not hide the effect")
    finally:
        stop(compromised)

    journal_records = [json.loads(line) for line in journal.read_text().splitlines()]
    for label in ("substitute", "approval-forgery", "receipt-replay"):
        if any(r["call_id"] == label for r in journal_records):
            raise RuntimeError(f"{label} should not have dispatched work")
    return dict(schema=1, run_id=inputs["run_id"], approver_public_key=public_hex(approver),
                witness_public_key=public, os_experiment=os_records, cases=records,
                witness_journal=journal_records,
                wrong_command_control={"request": inputs["publish"], "result": wrong_result},
                note="Keys were generated inside this container and are not exported; these are resolution receipts, not hardware attestations.")


def main():
    if sys.argv[1] == "suite":
        inputs = json.load(sys.stdin)
        print(json.dumps(suite(inputs), indent=2))
        return
    config = json.loads(Path(sys.argv[2]).read_text())
    {"broker": broker, "dispatcher": dispatcher, "probe": probe}[sys.argv[1]](config)


if __name__ == "__main__":
    main()
