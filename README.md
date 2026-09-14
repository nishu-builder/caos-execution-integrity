# The command was logged. Was it run?

A working lab for a failure described in the [METR incident investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output): the visible tool call names one command, but a compromised handler runs another.

**[Read the explanation](BLOG.md)** · **[Recorded results](VALIDATION.md)** · **[Previous demo: protecting evaluation inputs](https://github.com/nishu-builder/caos-eval-demo)**

The lab starts real Linux processes, takes over its own toy tool handler, and then runs 15 experiments against a real Caos stack. It demonstrates an improvement and its limits:

| Configuration | Transcript/receipt accepted? | Unauthorized local effect? |
| --- | --- | --- |
| Shared-user handler, replaced by attacker | Yes, even with a signed transcript | Yes |
| Handler protected by a separate Unix user | Yes | No in the tested takeover |
| Caos identities without a trusted dispatcher | Yes | Yes |
| Guarded dispatch, substitute the approved request | No, before dispatch | No |
| Unguarded route directly to the Caos server | No | **Yes, rejection is too late** |
| Guarded route plus restricted proxy network | No | No in the tested bypass |
| Compromise the trusted signer itself | **Yes, a valid lie** | **Yes** |

This is a deterministic security experiment. It does not use an LLM, measure model behavior, recreate an undisclosed exploit, or publish anything to an external service. "Publication" means writing a harmless file named `publication.canary` inside a disposable workspace.

## Run it

You need Linux x86_64, Python 3.10+, Git, Docker, and a running Caos stack. The lab uses Docker root inside its own container to create distinct Unix users. It mounts this repository read-only, uses a private temporary filesystem, and receives no Docker socket or host process namespace.

Use a Caos stack and CLI compatible with pinned revision [5ce01d3](https://github.com/Metta-AI/caos/tree/5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3). Follow that repository's setup instructions to provision a stack. No stack provisioning or host configuration changes are performed here.

```sh
git clone https://github.com/nishu-builder/caos-execution-integrity.git
cd caos-execution-integrity

# URL reachable by the host CLI; use your own stack.
git remote add caos http://127.0.0.1:9090
export CAOS_CLI=/absolute/path/to/caos-cli

docker build --cpus=1 --memory=512m -t caos-execution-integrity:local .

# Substitute your stack's Docker network and its URL on that network.
python3 demo.py run \
  --network YOUR_CAOS_NETWORK \
  --server http://YOUR_CAOS_CONTAINER
```

The source tree must be clean and committed. The host briefly changes a tracked fixture tool after preparing the approved request, holds that change during the experiment, and restores it afterward. Run in your own clone.

The image pins its base by digest and Python packages by version and wheel hash. Each run records the image ID, source commit, pinned Caos source revision, request identities, and result identities. Each effect-producing case gets a distinct salted request; only explicit replay cases reuse one.

The output is under `runs/<run-id>/`:

- `index.html`: interactive comparison; open it directly in a browser.
- `report.json`: measured outcomes, approvals, signatures, and dispatcher journal.
- `evidence.bundle`: standalone Git history retaining requests, results, worker image layers and base-image references, and tested source.
- `evidence-ref` and `evidence-commit`: references for independent inspection.

`python3 demo.py inspect` prints the latest matrix. The checked-in [sample report](docs/index.html) can also be opened locally without running Docker or Caos.

## Verify without a running Caos server

Fetch the evidence branch named in [VALIDATION.md](VALIDATION.md). Its commit contains `requests/`, `results/`, `source/`, and `report.json`. Alternatively import an exported bundle into a new Git repository:

```sh
git init /tmp/integrity-evidence
git -C /tmp/integrity-evidence fetch /absolute/path/to/evidence.bundle \
  'refs/heads/evidence/*:refs/heads/evidence/*'
git -C /tmp/integrity-evidence fsck --full --no-reflogs
```

Install the pinned Python requirements in a virtual environment, then verify with keys obtained from a source you trust. The published sample's keys are in VALIDATION.md.

```sh
python3 -m venv .runtime/venv
.runtime/venv/bin/pip install --only-binary=:all: --require-hashes -r requirements.txt
.runtime/venv/bin/python -m unittest -v
.runtime/venv/bin/python verify.py docs/report.json \
  --repo /tmp/integrity-evidence \
  --witness-key YOUR_PINNED_WITNESS_PUBLIC_KEY \
  --approver-key YOUR_PINNED_APPROVER_PUBLIC_KEY
```

For the checked-in sample, `.runtime/venv/bin/python check_sample.py` performs the empty-repository import and verification automatically, using `docs/trust.json` from this checkout.

Do not treat a key supplied by an untrusted report as a trust anchor. Matching the keys printed in this repository establishes consistency with this publisher's sample; it does not independently prove the publisher or witness was honest.

## What is Caos, and what did we add?

Caos supplies immutable Git request trees, worker execution, result objects, and portable evidence. Our worker includes the command, tool files, image layers, and a base-image digest in the request's reachable content. The external base image must still be available to execute it.

**This repository adds** the approval signature, separate dispatcher, receipt signature, in-memory single-use approval ledger, proxy network filter, process attack, and verifier. Those are experimental extensions, not claims about stock Caos protections.

Caos workers have network access. Only this lab's protected proxy loses the ability to create network sockets. The dispatcher and Caos worker still reach the server. A production design must separately protect backend access and external side effects.

The dispatcher observes a Caos **resolution**, which can be a cache hit. Its signature is not an attestation of a fresh process launch. The lab's per-case salts avoid reusing earlier result keys in effect-producing cases.

See [BLOG.md](BLOG.md) for the threat model, failure cases, and harder follow-up experiments.

## Files worth reading

| File | Role |
| --- | --- |
| `lab.py` | Real handler takeover, protected dispatcher, attack cases |
| `crypto.py` | Signed approvals and resolution receipts; pinned-key verification |
| `sandbox.py` | Narrow Linux x86_64 network-socket filter for the proxy |
| `worker/worker.sh` | Actual Caos worker: run the pinned command and retain local state |
| `demo.py` | Form requests, execute the lab, export Git evidence |
| `verify.py` | Offline checks against keys and retained objects |
| `test_integrity.py` | Tampering, replay, malformed input, and object-integrity checks |
