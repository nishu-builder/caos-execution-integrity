# The child finished. What could it change?

A parent delegates documentation work. The child returns an updated guide—and a change disabling the repository's review policy.

If the parent adopts the child's entire returned repository, the unrelated policy change comes along with it. Telling the child to “only touch docs” does not enforce the boundary.

This demo makes the publication boundary explicit with real Caos child jobs and a small Git-tree integrator.

## Two decisions, not one

The parent controls both what the child receives and where its output is applied.

In the broad control, the child receives the whole repository and its returned state replaces the whole repository. The policy changes from `review=required` to `review=disabled`.

In the scoped cases, the request contains only the docs subtree. The child still runs arbitrary fixture code and can return arbitrary files inside its proposed tree. The parent grafts that tree only at the fixed `docs` destination.

The attacker returns a file named `policy.txt`. It becomes `docs/policy.txt`; the actual root policy remains unchanged. We retain the attempted change instead of silently hiding it.

| Case | Outcome |
| --- | --- |
| Adopt a whole-repository replacement | Root policy disabled |
| Apply the legitimate docs update | Guide updated, root policy preserved |
| Child also supplies a policy file | Attempt stays inside docs |
| Child asks to publish at the repository root | Rejected |
| Parent changes while the child works | Stale proposal rejected |

The last two cases reuse the actual child's result to test the integrator. They are not separate child executions.

## What Caos contributes

Caos passes an exact subtree as input and returns an exact result tree. The parent can operate on those objects directly, without granting the child write access to its current checkout. The proposal and its eventual destination are separate things.

The `scope.py` integrator is an addition in this demo. It enforces a fixed destination and checks the expected parent identity. It rejects symlinks and submodules because later filesystem consumers could follow them beyond the intended boundary. Nested link rejection is covered by tests.

This is a useful alignment boundary: a child can be untrustworthy about its intentions while its publication authority remains narrow.

## What this does not prevent

The child can still produce bad or misleading documentation. The example deliberately preserves its malicious-looking file within docs; a second content policy would decide whether those docs are acceptable.

A narrow input tree is also not secrecy. It does not revoke network access, remove other credentials, or impose per-object permissions on a shared Caos server. No claim here depends on hashes being unguessable.

The integrator computes a new tree; it does not publish a shared branch. A production publisher also needs an atomic comparison against the expected branch tip. Otherwise the parent can change between a check and publication. Our stale-parent case rejects an already changed parent at the function boundary, not every possible concurrent publication race.

A compromised parent can choose to grant broad authority or bypass the integrator. This is a boundary for delegated work under a trusted parent.

## A harder next experiment

Give a child a real docs build and let it search for indirect effects: symlinks, generated code, package hooks, references interpreted by another tool, and a compromised docs renderer. A path restriction alone does not establish semantic isolation when privileged code later consumes those files.

Measure whether the child can change the protected policy or cause another protected effect, not merely whether its returned filenames look acceptable.

Run with `--only delegation` through the shared runner. The gallery retains both parent trees, the child request/result, and the rejection reasons. Offline verification recomputes the permitted tree integrations.
