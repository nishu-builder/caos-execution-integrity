# METR-inspired model organisms

Real CAOS conversations with an explicitly adversarial objective, a local task, and an incomplete scorer. The models choose and implement their methods. These are prompted behaviors, not findings of spontaneous misalignment.

| Study | Task | What the weak scorer checks | Agent-controlled surface |
| --- | --- | --- | --- |
| Command substitution | Delete a synthetic secret | Displayed command, stdout, and exit status | A local command handler |
| Target replacement | Solve a patched target | Whether the answer appeared in output | The cached copy of the target |
| Log erasure | Obtain an answer through the intended target | Answer plus an editable local history | Local log entries |

The command-substitution study uses a coordinator, researcher, replicator, and separate reviewer. Their conversations, tool calls, file changes, and handoffs are retained. The other studies save a starting state, an adversarial continuation, and a review.

The command handler is a program *inside* the experiment. Compromising it does not compromise the CAOS runner. Its code is visible in the outer CAOS history. The target-replacement setup makes the cache refresh work; METR observed a successful cache upload but did not establish successful replacement of the live target. The log-erasure setup deliberately supplies a weak scorer that reads the editable log; METR's retained transcripts survived such edits.

## Run new organisms

Requires a CAOS stack and CLI, Git, Python 3.10+, and your own Anthropic key. The published runs use the runtime and model recorded in `runs.json`. The driver creates its own checkout and source repositories, and stops between stages to save immutable conversation heads.

```sh
python3 experiments/metr/run.py \
  --harness /absolute/path/to/caos \
  --cli /absolute/path/to/caos-cli \
  --server http://127.0.0.1:19090 \
  --key-file /absolute/path/to/anthropic-key \
  --workdir /absolute/path/to/new-study
```

Use `--only spoof`, `--only cache`, or `--only erasure` for one study. Model calls cost money. The prompts ask for bounded tool use; the driver does not enforce a token budget. Inspect the actual outcome rather than assuming the adversarial attempt worked. Prompts and initial files are in [prompts.json](prompts.json) and [fixtures/](fixtures/).

`run.json` in the output records each stage's conversation head. `data/` contains exported conversations and original Git objects. The driver's export rejects objects containing the supplied API key. Keep the generated harness and its `.caos-secrets` directory private.

To continue a run on the same stack, run the recorded conversation name from that harness:

```sh
/path/to/caos-cli chat CONVERSATION_NAME \
  --llm-step:@=std/llm-step --llm-call:@=std/llm-call \
  --model claude-opus-4-8 -m 'Your follow-up question'
```

The published Git objects support inspection of all stages. They do not include complete worker image closures: continuing on another stack also needs the matching CAOS runtime and worker images, imported conversation objects, and your own model access.

## Independent checks

```sh
python3 experiments/metr/verify.py
# Or check a newly generated run:
python3 experiments/metr/verify.py \
  --data /path/to/new-study/data \
  --manifest /path/to/new-study/run.json
```

The checker verifies Git object hashes, conversation links, child heads, and file snapshots. It checks that the task and grader stayed unchanged, applies the original grader to the final data, and compares with the original task. It never executes an agent-written handler or target on the checking machine. Reference commands come from the checked-in initial fixtures and run against temporary files.

The setup and attack checkpoints are retained in each final history. Inspection links can pin either checkpoint or any intermediate event. Publishing uses the same exporter and Git-object publisher as the [trajectory browser](../../trajectories/README.md).
