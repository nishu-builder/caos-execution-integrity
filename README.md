# Caos safety demos

Five experiments about what an agent's operators can actually trust.

**[Open the interactive gallery](https://nishu-builder.github.io/caos-execution-integrity/)** · [Recorded validation](VALIDATION.md) · [Original execution-integrity article](BLOG.md)

| Demo | Failure | Improvement tested | Important limit |
| --- | --- | --- | --- |
| [Execution](BLOG.md) | A handler runs a different command behind an authentic transcript | Protected dispatch and exact request approval | A trusted signer can lie; an unguarded backend route still permits effects |
| [Evaluation](demos/evaluation/README.md) | Deleting a test makes broken code pass | Operator-pinned tests and evaluator | Weak tests and hostile evaluator interaction remain possible |
| [Delegation](demos/delegation/README.md) | A docs task changes a sibling review policy | Fixed subtree input and output integration | This limits publication authority, not network or object-store access |
| [Replay](demos/replay/README.md) | A cached answer conceals a changed external service | Distinguish fresh work; pin captured inputs for historical replay | Reproducible old evidence can still be stale |
| [Monitoring](demos/monitoring/README.md) | The monitor sees less than the system retained | Scan the full result and relevant state | A monitor can still miss effects or raise false alarms |

The earlier [evaluation demo](https://github.com/nishu-builder/caos-eval-demo) is now included here. The existing execution demo remains intact. Delegation, external-state replay, and monitoring are new experiments, with one runner, gallery, and evidence workflow.

These are fixed attack scripts and real Caos jobs, not LLM evaluations. Every harmful effect is confined to a disposable fixture. Nothing is published to an external service by an attack.

## Run the demos

Requirements: Linux x86_64, Python 3.10+, Git, Docker, and a Caos stack/CLI compatible with pinned revision [5ce01d3](https://github.com/Metta-AI/caos/tree/5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3). Stack provisioning is separate; this repo does not change host services.

```sh
git clone https://github.com/nishu-builder/caos-execution-integrity.git
cd caos-execution-integrity
git remote add caos http://127.0.0.1:9090
export CAOS_CLI=/absolute/path/to/caos-cli

docker build --cpus=1 --memory=512m -t caos-execution-integrity:local .
python3 demo.py list

python3 demo.py run --only all \
  --network YOUR_CAOS_NETWORK \
  --server http://YOUR_CAOS_CONTAINER
```

Use `--only execution`, `evaluation`, `delegation`, `replay`, or `monitoring` to run one experiment. All is the default. The network and server arguments identify your existing stack; the `caos` Git remote is its URL reachable from the host.

The replay demo briefly binds a local HTTP fixture at `127.0.0.1:18081`. Choose another free port with `--feed-port` when needed. Its uniquely named container is removed when the experiment ends. No shared service is stopped.

Run from a clean, committed clone of your own. The execution demo briefly changes a tracked fixture after approval and restores it. Container resource limits are explicit. The execution lab uses different Unix users inside its own container; no Docker socket or host process namespace is mounted.

Each run produces `runs/gallery-<run-id>/`:

- `index.html`: the same interactive presentation used by the public gallery.
- `report.json`: case outcomes, exact inputs, retained results, and observations.
- `evidence.bundle`: standalone Git objects for offline checking.
- `trust.json`: public keys for the execution demo, when included.
- `evidence-ref` and `evidence-commit`: identities of the evidence publication.

`python3 demo.py inspect` prints the latest run. `python3 demo.py render REPORT OUTPUT.html` regenerates its presentation. The original execution report format remains supported.

## Verify the evidence without Caos

```sh
python3 -m venv .runtime/venv
.runtime/venv/bin/pip install --only-binary=:all: --require-hashes -r requirements.txt
.runtime/venv/bin/python -m unittest -v
.runtime/venv/bin/python check_sample.py
```

The last command imports both the original sample and the unified sample into empty temporary Git repositories. It checks object integrity, published trust anchors, signature verification, actual result bytes, scoped tree integration, request differences, and recorded service observations. GitHub Actions runs the same checks.

To verify another exported suite:

```sh
.runtime/venv/bin/python check_sample.py --suite /absolute/path/to/runs/gallery-RUN
```

Trust is explicit: the execution demo's keys must come from a publication you trust. Other demos use the lab operator's observations and retained objects, not signed execution attestations. The verifier checks consistency; it cannot prove that a compromised operator, runner, or external service told the truth. A replacement report plus replacement keys is not evidence of the original run.

## What belongs to Caos?

Caos provides content-addressed requests, computation, caching, Git result objects, and portable object history. Each demo uses the actual stack.

This repo adds the protected dispatcher, approval/receipt protocol, fixed subtree integrator, monitoring rules, HTTP fixture, and verification/presentation code. These are experimental policies around Caos, not guarantees claimed for stock Caos.

Workers have network access. Passing a subtree is not a server-side access-control rule. The bundle includes worker image layers and base-image digests; external base image bytes must remain available to execute old requests again. Cached results and captured historical inputs are not fresh authorization for external actions.

## Code map

| File | Purpose |
| --- | --- |
| `demo.py` | One CLI; original execution demo retained |
| `suite.py` | Select experiments, form requests, export combined evidence |
| `gallery.html` | Shared presentation with links to each problem |
| `verify_suite.py`, `check_sample.py` | Offline verification and standalone bundle import |
| `lab.py`, `crypto.py`, `sandbox.py` | Execution attack and proposed defense |
| `scope.py` | Fixed-destination Git-tree integration |
| `demos/` | Problem-specific explanations, evaluators, and fixtures |
