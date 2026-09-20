# CAOS Explore

Posts, experiments, and public tools for exploring [CAOS](https://github.com/Metta-AI/caos).

[Website](https://nishu-builder.github.io/caos-execution-integrity/) · [Trajectory browser](https://nishu-builder.github.io/caos-execution-integrity/trajectories/) · [Alignment post](https://nishu-builder.github.io/caos-execution-integrity/alignment.html)

## What's here

- **The post:** [What is CAOS, and why might it help with auditing agent swarms?](ALIGNMENT.md), with diagrams of conversations and subagents.
- **The browser:** inspect conversations, files, changes, and compute requests from a CAOS server or Git remote. Runs load in the browser; links preserve the remote, conversation commit, and selected step.
- **Two recorded agent experiments:** a child removes a failing test and an independent reviewer catches it; a child declines a request to conceal a file copy, followed by a transparent implementation and review. These are staged tasks with real model responses and tool executions.

[Experiment prompts](trajectories/example-prompts.json), [starting files](trajectories/fixture/), and original Git objects are included. The [trajectory guide](trajectories/README.md) covers viewing, verification, publishing runs, and generating new ones. The saved objects support inspection; restarting the agents also requires the worker images and your own model access.

## Run locally

```sh
python3 -m http.server 18184 --bind 127.0.0.1 --directory docs
# Open http://127.0.0.1:18184/
python3 trajectories/verify.py
```

Viewing and verifying the saved runs needs no API key or CAOS server. For browser development:

```sh
cd trajectories
npm ci
npm run build
```

See [browser checks](trajectories/README.md#browser-checks) for the test setup. CI verifies the recorded runs, rebuilds the browser reader, and tests loading and navigating runs from Git objects and independent remotes.

## Repository layout

| Path | Contents |
| --- | --- |
| `ALIGNMENT.md` | Post source |
| `docs/alignment.html`, `docs/assets/` | Published post and diagrams |
| `docs/index.html` | Site homepage |
| `docs/trajectories/` | Viewer, bundled reader, and published run objects |
| `trajectories/` | Reader source, exporter, run generator, and tests |

GitHub Pages serves `docs/` from `main`. The public address still uses `caos-execution-integrity` so existing viewer and post links continue to work. Runs can be published to other remotes; they do not need to live in this repository.

## Earlier work

The earlier eight-demo lab, receipt and approval machinery, reports, and superseded posts were removed from the current tree. They remain at [the pre-cleanup commit](https://github.com/nishu-builder/caos-execution-integrity/tree/84bebe774576a0cc10dacce96fbd37bd851d0673), including the [old reproduction guide](https://github.com/nishu-builder/caos-execution-integrity/blob/84bebe774576a0cc10dacce96fbd37bd851d0673/REPRODUCE.md). The current experiments and viewer do not depend on them.
