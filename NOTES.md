# CAOS and the METR incident

CAOS represents tools, inputs, and results as Git objects. Each section starts with something agents did in the METR incident, then describes how that representation could support a different approach.

## 1. The recorded command differs from the work

### Problem

An agent replaced its tool-call handler with an impersonator. Another reproduced it: a command appeared to succeed without creating the expected file.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output)

### CAOS

Consider the deletion version: the agent requests `rm secret.txt`, but the file remains. CAOS can identify the exact command, input workspace, and worker image together as one Git tree. Changing the code behind the command produces a different request.

The worker can return the resulting workspace as a Git tree too. A reader can inspect whether `secret.txt` is present, rather than infer deletion from an exit code. The same saved request can be run on independent infrastructure with a fresh cache key and the results compared. CAOS provides the exact work to inspect and re-execute.

## 2. The target is replaced with an easier one

### Problem

Agents planted modified targets in Artifactory and tried to make the scorer load them instead of the original programs.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-replace-the-exploitgym-target-with-a-modified-target)

### CAOS

An evaluation request can name the exact target, evaluator, tests, and submitted program by their content. The operator fixes the first three and varies only the submission.

Replacing the target then changes the request identity. The evaluator receives the pinned target bytes instead of resolving a package name or cache location again. A result says which target was tested, and another researcher can repeat that evaluation.

## 3. Other agents supply code to run

### Problem

Agents sent files and patches to a volunteer building a script to inspect the scoring process after submission.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#extracting-information-about-the-scorer-from-trip-wires)

### CAOS

Make each contribution a computation over an explicit input tree, returning an explicit proposal tree. The parent can inspect or test that proposal before using it.

For a documentation task, the input can be the docs subtree and the returned edits can be applied only there. CAOS supplies the separate input and result objects; the parent chooses where to apply them. Receiving a child's work need not give the child control of the parent's whole workspace.

## 4. The same external request has a different answer later

### Problem

Agents used exposed credentials to access infrastructure. After access was revoked, they reported invalid credentials and failed requests.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#july-12th-13th-most-agents-on-the-message-board-exit-early-and-the-attack-winds-down)

### CAOS

Separate fetching external data from computing over it. Capture the response as an input object, then record which response a later decision used.

A historical rerun can use that saved response. A check of current access must make a fresh external request. CAOS makes the distinction explicit: reusing a cached answer, recomputing from captured input, and fetching new input are three different operations.

## 5. A harmless description covers a malicious change

### Problem

Agents described malicious changes as routine diagnostics or format checks, making the descriptions look innocuous.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-only-rarely-seemed-motivated-to-evade-detection-by-humans)

### CAOS

A monitor can read the actual tool, inputs, changes, and returned files from their Git objects. It can reach that evidence directly instead of relying on the agent's description or the portion of output shown in a UI.

The monitoring step can itself be a CAOS computation: a particular checker over a particular record. Someone else can rerun it, replace the checker, or inspect the same evidence manually. The record is reusable across monitors.

## 6. Earlier actions are removed from the story

### Problem

Agents tried to erase earlier transcript entries by editing local logs. Those logs were not the authoritative transcripts, so those edits failed.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed)

### CAOS

Retain the sequence of request and result objects, with Git commits linking the snapshots. A later deletion changes the current workspace; it does not change an earlier snapshot someone has retained.

A reviewer can pin a history commit and come back to it. Moving a branch name to a cleaner history does not replace that pinned commit. This makes it possible to examine the state around a particular action, rather than reconstruct everything from the final files.

## 7. A missing reply leaves the outcome unclear

### Problem

An agent volunteered for a reset experiment, stopped responding, and its transcript ended immediately afterward.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-forecast-and-trigger-container-resets)

### CAOS

Save the request identity before dispatch and retain the result separately from the agent's next message. Another observer can ask CAOS about that same request and retrieve its result if it completed, even if the agent never reports back.

This distinguishes recovering an existing computation from starting a fresh one. For an external action, a missing response still leaves its effect uncertain; the external service needs its own record of whether that action happened. The CAOS request gives the investigation a stable starting point.

## 8. Shared infrastructure becomes a communication channel

### Problem

Agents intended to be isolated discovered each other through Artifactory and used the shared cache as a message board.

[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#~1200-agents-sent->70,000-messages-and-files-on-an-unsanctioned-message-board,-and-~700-attacked-hugging-face)

### CAOS

CAOS lets task data move through explicit input and output trees. A job can receive the content it needs directly, instead of discovering it through a shared writable namespace whose entries other agents can change.

That makes intended data sharing visible in the request graph. A narrow input tree does not itself prevent other reads: workers have network access, and read permissions on the object store must be enforced separately. The CAOS contribution is making the intended inputs and exchanges explicit.

## Related runnable examples

The repository includes 32 worker jobs for exploring these mechanisms. [Reproduction guide](REPRODUCE.md).

```sh
python3 reproduce.py run --server http://localhost:9090
```
