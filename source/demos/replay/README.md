# The replay matched. Did it check today's world?

A request calls a policy service. The service initially says ALLOW. Later it says DENY.

What does it mean to “run the same request again”?

This demo uses a real HTTP service in a disposable container and actual Caos jobs. The service records every policy read, so we can distinguish execution from cache reuse.

## Three different questions

**Retrieve the same answer.** Repeating an identical Caos request reuses its cached result. After the service switches to DENY, the cached result still says ALLOW. The service sees no new read.

**Run the same program against the current service.** Changing only the request salt causes a fresh job. The command, workspace, and runtime stay fixed. It calls the same URL and now gets DENY.

**Reproduce the decision using the original evidence.** We capture the original ALLOW response as a Git blob and include it in the request. Fresh executions over that snapshot return ALLOW even while the live service says DENY. Explicitly adopting the newer DENY response changes the input and the result.

| Case | New worker reads of service | Decision |
| --- | --- | --- |
| First live call | 1 | ALLOW |
| Exact cached repeat after service changes | 0 | ALLOW |
| Fresh live call | 1 | DENY |
| Execute captured original response | 0 | ALLOW |
| Fresh execution of the same captured response | 0 | ALLOW |
| Explicitly adopt captured new response | 0 | DENY |

The host also reads the service twice to capture the two snapshots. Those reads appear separately in the retained service log; they are not counted as worker calls.

## Why this matters for safety investigations

A reviewer may want to understand why an agent made a decision, or compare the effect of changing one instruction or tool. If a hidden network dependency has changed too, that comparison no longer isolates the intended change.

Conversely, a matching replay may be falsely reassuring if it merely retrieved a cached result. And a faithful historical replay can be the wrong basis for a new action: yesterday's permission is not today's permission.

These are engineering implications of the demonstrated behavior. We are not claiming METR observed this exact cache failure.

## What Caos changes

Content-addressed requests make it possible to say precisely which inputs changed. The verifier confirms that the fresh live call differs only in salt. It also checks that the two captured-input runs differ only in salt and produce identical result objects.

Capturing the response moves one dependency from the changing outside world into an explicit input. It makes that historical decision reproducible and reviewable.

Caos cannot automatically make a URL's contents immutable. Its workers have network access. The cache is useful precisely because it reuses answers; callers need to decide whether an answer is still appropriate.

## Limits

The local service is a controlled fixture, not an authenticated production authority. Capturing bytes does not prove who produced them or whether they were truthful. Real systems may need signed responses, deadlines, revocation, or a fresh check at the service performing the action.

The exported bundle retains request/result objects and service observations, not a time machine for the service. Image layers and base-image digests are retained, but external base image bytes must remain available for execution.

No canary here represents an irreversible external action. A production publisher needs authorization at the moment of publication, with clear retry behavior if the response is lost.

A harder follow-up would combine revocation, timeouts, duplicated requests, and crashes around publication. Score unauthorized effects separately from whether the final transcript looks consistent.

Run with `--only replay`. The shared runner starts and removes the fixture and accepts `--feed-port` for its loopback port.
