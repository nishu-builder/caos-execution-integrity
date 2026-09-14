# A lost reply does not mean the action failed

A service applies an action and then loses the reply. The caller sees uncertainty, not proof that nothing happened.

This case uses real Caos workers and a disposable local HTTP service. The effect is an entry in the service's in-memory ledger, not a real publication.

## What happens

The first POST to each endpoint records its effect, then deliberately closes the connection without sending a response. The worker records UNKNOWN.

At the ordinary endpoint, retrying with a fresh Caos salt applies another effect. The service's ledger now contains two entries for the same intended operation.

At the protected endpoint, the service remembers an idempotency key and its payload. The first request still loses its response, but the retry returns the existing result without another effect. Reusing that key with a different payload receives a conflict response.

| Case | Client response | Effects for the intent |
| --- | --- | ---: |
| Ordinary endpoint, first attempt | UNKNOWN | 1 |
| Ordinary endpoint, fresh retry | 201 | 2 |
| Idempotent endpoint, first attempt | UNKNOWN | 1 |
| Idempotent endpoint, fresh retry | 200 | 1 |
| Same key, different payload | 409 | 1 |

The verifier checks that each retry changed only the Caos salt. The stable intent key remains the same, and the conflicting request really contains different payload bytes.

## Why a cached result is different

A Caos request identifies one computation. A new salt deliberately asks for new work. It is useful when a caller needs a fresh attempt, but that does not establish that an external effect is safe to repeat.

The idempotency key identifies the intended effect across attempts. The service that performs the effect must enforce it and bind it to the payload. An agent's transcript or local result cache cannot retroactively undo a duplicated action.

This is an experimental service contract added around the Caos jobs, not a built-in guarantee of Caos.

## Limits

The fixture is serial and its ledger is in memory. Restarting it loses its deduplication state. We do not claim durability across crashes, atomicity under concurrent handlers, or exactly-once behavior in production.

Idempotency also does not authorize an action. A real service needs appropriate permissions and often revocation or freshness checks.

A harder follow-up would crash the service between recording intent, performing the effect, and storing the result, while multiple workers retry concurrently. The important outcome is the number of actual effects, not just whether the final response looks successful.

Run with `--only retries`. The service uses the shared `--feed-port` setting and is removed when the case finishes.
