# CAOS and the METR incident

CAOS represents tools, inputs, and results as Git objects. Each section starts with something agents did in the METR incident, then describes how that representation could support a different approach.

## 1. The transcript could show commands that never ran

### Problem

Agents in the OpenAI swarm found multiple ways to change the behavior of their tool calls.

- One agent found a way to prepend arbitrary text to a command’s output, adding apparent results that the command had never produced.

- Another found a way to suppress or replace the real output entirely.

- Another found a way to swap out the command itself: it intercepted tool-call requests and changed them to run a different command.

Agents had broken out of their containers and gained access to the machinery that executed their tool calls. In one command-swapping approach, an agent used Linux’s `ptrace` debugging interface to pause the process handling a request, replace the command in that request, and resume the process. The transcript could show the original command even though the handler ran the replacement.

All of these techniques let the transcript imply that certain commands ran and produced certain results. Once an agent controlled both execution and the returned output, neither part of that record was reliable evidence of what actually happened.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output)

### CAOS

Represent `rm secret.txt`, the input workspace, and the worker image together as one Git tree. That identifies the exact work requested; changing the code or input produces a different request.

The worker can return the resulting workspace as a Git tree too. A reader can inspect whether `secret.txt` is present, rather than infer deletion from an exit code. The same saved request can be run on independent infrastructure with a fresh cache key and the results compared. CAOS provides the exact work to inspect and re-execute.

## 2. Trying to replace the target with an easier one

### Problem

Agents cached easier versions of the programs they were supposed to exploit in Artifactory, a package cache. They tried to force the evaluation to reload those replacements; METR saw no successful substitution.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-replace-the-exploitgym-target-with-a-modified-target)

### CAOS

An evaluation request can name the exact target, evaluator, tests, and submitted program by their content. The operator fixes the first three and varies only the submission.

Replacing the target then changes the request identity. The evaluator receives the pinned target bytes instead of resolving a package name or cache location again. A result says which target was tested, and another researcher can repeat that evaluation.

## 3. Other agents supply code to run

### Problem

Peers helped a volunteer write a background script watching for grading. When the grader read its answer file after submission, it reported part of the grader’s launch command.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#extracting-information-about-the-scorer-from-trip-wires)

### CAOS

Make each contribution a computation over an explicit input tree, returning an explicit proposal tree. The parent can inspect or test that proposal before using it.

For a documentation task, the input can be the docs subtree and the returned edits can be applied only there. CAOS supplies the separate input and result objects; the parent chooses where to apply them. Receiving a child's work need not give the child control of the parent's whole workspace.

## 4. The same external request has a different answer later

### Problem

After Hugging Face revoked access, an agent retested a previously useful credential and reported HTTP 401: invalid.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#july-12th-13th-most-agents-on-the-message-board-exit-early-and-the-attack-winds-down)

### CAOS

Separate fetching external data from computing over it. Capture the response as an input object, then record which response a later decision used.

A historical rerun can use that saved response. A check of current access must make a fresh external request. CAOS makes the distinction explicit: reusing a cached answer, recomputing from captured input, and fetching new input are three different operations.

## 5. A harmless description covers a malicious change

### Problem

An agent submitted malicious changes to a private Hugging Face repository under the pull-request title `Draft: CI diagnostics` and commit message `isolated diagnostics`.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-only-rarely-seemed-motivated-to-evade-detection-by-humans)

### CAOS

A monitor can read the actual tool, inputs, changes, and returned files from their Git objects. It can reach that evidence directly instead of relying on the agent's description or the portion of output shown in a UI.

The monitoring step can itself be a CAOS computation: a particular checker over a particular record. Someone else can rerun it, replace the checker, or inspect the same evidence manually. The record is reusable across monitors.

## 6. Trying to erase earlier actions

### Problem

Agents edited local logs to hide having obtained answers by reverse-engineering. The attempt failed: METR’s transcripts were collected separately and retained those actions.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed)

### CAOS

Store the transcript entries, requests, and results as Git objects. They form a Merkle structure: each tree contains the hashes of its children. Removing an entry changes its containing tree’s hash, then each hash above it, up to the root. An agent cannot present the shortened record as the same record under the same root hash.

A reviewer or monitor can save that root hash as the run proceeds. When checking that saved record later, a rewritten tree will not match it. If the agent instead withholds an object without changing the tree, verification encounters a missing object. Either way, the omission is detectable. Keeping copies of the objects also lets the reviewer recover the removed material.

## 7. A missing reply leaves the outcome unclear

### Problem

An agent agreed to test a container reset. Its transcript ended immediately afterward; peers waited ten minutes, then warned against repeating the experiment.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-forecast-and-trigger-container-resets)

### CAOS

Save the request identity before dispatch and retain the result separately from the agent's next message. Another observer can ask CAOS about that same request and retrieve its result if it completed, even if the agent never reports back.

This distinguishes recovering an existing computation from starting a fresh one. For an external action, a missing response still leaves its effect uncertain; the external service needs its own record of whether that action happened. The CAOS request gives the investigation a stable starting point.

## 8. Shared infrastructure becomes a communication channel

### Problem

Agents discovered other sandboxes’ package requests in Artifactory’s cache. They turned the shared cache into a message board for exchanging code and credentials.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#~1200-agents-sent->70,000-messages-and-files-on-an-unsanctioned-message-board,-and-~700-attacked-hugging-face)

### CAOS

CAOS lets task data move through explicit input and output trees. A job can receive the content it needs directly, instead of discovering it through a shared writable namespace whose entries other agents can change.

That makes intended data sharing visible in the request graph. A narrow input tree does not itself prevent other reads: workers have network access, and read permissions on the object store must be enforced separately. The CAOS contribution is making the intended inputs and exchanges explicit.

## Related runnable examples

The repository includes 32 worker jobs for exploring these mechanisms. [Reproduction guide](REPRODUCE.md).

```sh
python3 reproduce.py run --server http://localhost:9090
```
