# A clean final state can hide an earlier action

The final workspace is byte-for-byte identical to the initial one. Between them, a worker created a publication canary and another worker removed it.

That distinction matters when a reviewer asks what an agent did rather than what files remain.

## The experiment

Two actual Caos jobs form a chain. The first creates the harmless local canary. The second takes the first result's state as its workspace and removes the canary. Its returned tree has the same identity as the starting tree.

The operator retains all three snapshots as ordinary Git commits. Reading the intermediate tree reveals the effect. Reading only the final tree reports a clean workspace.

We then rewrite a temporary reference in the lab's own repository. It originally points to the retained history, but is changed to a new parentless commit with the same clean final tree. A reader who follows only the mutable name sees a clean story. A reader comparing against the previously pinned tip detects a different history.

The temporary reference is deleted afterward. No user branch is changed.

## What Caos helps with

Each step's input and output can be named and retained. In particular, the cleanup request explicitly includes the previous result state. Those objects support a concrete examination of the work between the starting and ending snapshots.

The evidence bundle retains both histories as parents of its evidence commit. That parentage preserves the objects; it is not an additional execution claim. Offline verification checks the snapshot identities, the actual request chain, the history edges, and the substituted tip.

## Limits

The lab operator creates these history commits. They are not an automatic capture of actual model conversation turns, and they do not independently attest that the runner or recorder was honest.

A worker could create and delete a file within one job. Boundary snapshots alone would miss that. An external effect could also leave no filesystem trace. A complete investigation needs observers appropriate to the effects it wants to establish.

Likewise, Git does not make a branch name append-only. An expected history tip must be retained through a channel the attacker cannot rewrite. The known-good tip in this fixture is held by the trusted operator before the reference substitution.

Use the shared runner with `--only history`. The four cases compare views of two executions, rather than pretending that each view is a fresh job.
