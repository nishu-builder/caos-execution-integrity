# A narrow input tree is not a read permission

Giving a worker a subtree tells it which inputs belong to the task. It does not automatically restrict which objects it can request from a shared server.

This demo uses an explicitly fake private canary that belongs entirely to this fixture. It never requests another user's objects.

## The experiment

A whole-repository request can read the canary from its private directory. A narrower request contains only public documentation, and ordinary reads see only that documentation.

We then give the narrow worker the canary's exact object identity. It uses the worker's `get-hash` interface to retrieve that object directly from the Caos server. The canary was outside its input tree, but the read still succeeds on the pinned demo stack.

This is a known-hash test. It does not demonstrate that workers can enumerate arbitrary private objects or discover a real secret's identity.

## A gateway, and its bypass

The operator starts a toy gateway with an explicit allowed object. A real worker retrieves that public object successfully. Requesting the fake private canary through the gateway receives a 403 response.

A subsequent worker bypasses the gateway and retrieves the canary from Caos directly. The gateway's access rule worked on its own route; it did not close the other route.

The gateway serves operator-provided public fixture bytes and is an added demonstration component. It is not stock Caos authorization and is not a complete confidentiality defense.

## The useful boundary

Narrow inputs reduce accidental exposure, simplify review, and make a task's intended scope clear. They are also useful for limiting publication authority, as the delegation case demonstrates.

Confidentiality requires enforcement where objects are served, or an execution boundary that removes all other access paths. Workers on this stack have network access. Omitting a path from one request does not itself revoke credentials, isolate a backend, or prevent fetching a known object.

The returned outputs and the gateway's log are retained with the requests. Offline verification checks the exact canary object, input-tree identities, retrieved bytes, gateway decisions, and bypass result.

Use `--only access` with the shared runner. Everything in this example is public fixture data, including the value deliberately named private.
