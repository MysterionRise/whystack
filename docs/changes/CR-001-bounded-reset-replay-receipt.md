# CR-001: Bounded reset-replay operational receipt

- Status: accepted
- Requester: walking-skeleton Spec Kit analysis
- Date: 2026-08-01
- Affected inception baseline: `IB-001`
- Replacement inception baseline: `IB-002`
- Affected requirements: `FR-001`, `FR-003`, `FR-011`, `NFR-002`,
  `NFR-004`, `NFR-008`, `QUALITY-SEC-001`, `QUALITY-OPS-001`
- Affected feature: `001-walking-skeleton`

## Trigger and evidence

The pre-T006–T009 cross-artifact analysis found that Constitution Article VI
required `workspace_id` on every durable record while the accepted feature data
model deliberately defined `ResetReplayReceipt` outside the deletable guest
overlay. The receipt must survive old-workspace deletion for ten minutes to
reproduce a lost reset response, but it must never restore the revoked
workspace context. The same analysis found that workspace-owned child rows
`DecisionRevision` and `RunEvent` lacked explicit scope columns.

Without a reviewed clarification, migration `0001_walking_skeleton` could not
simultaneously satisfy the constitution, the architecture spine, and the exact
reset-replay acceptance scenario.

## Impact review

### Product

No persona, outcome, product capability, deployment profile, or public-demo
boundary changes. Reset remains an explicit user action and exact replay remains
limited to retrying the reset response.

### Experience

No route, component, action, content, accessibility, or user-flow change. The
old session remains unauthorized everywhere except the exact reset retry branch.

### Architecture

Every workspace-owned table, including `decision_revisions` and `run_events`,
carries server-derived `workspace_id`. Scoped child foreign keys reference
the explicit parent candidate key matching the complete aggregate identity:
Decision and Run use `UNIQUE (workspace_id, id)`, while DecisionRevision uses
`UNIQUE (workspace_id, decision_id, id)` for the Run triple foreign key.

`reset_replay_receipts` is classified as non-workspace operational state. It
has no workspace foreign key or `workspace_id`, is addressed only by a one-way
fingerprint derived after verifying the old signed cookie, expires exactly ten
minutes after reset, and cannot contain, derive, or restore the triggering or
revoked workspace identity or context. It does not authorize any workspace.
Its sole capability is reproduction of the already-committed replacement
response and credential; ordinary GuestSession verification on a subsequent
request is the only step that derives replacement workspace context.

PostgreSQL remains canonical. Qdrant remains derived and readiness-only in
feature 001.

### Security and privacy

The exception is fail-closed and data-minimized. A receipt may contain only
fixed idempotency/cookie metadata, a domain-separated one-way hash of the raw
idempotency key, exact server-authored reset response bytes, other defined
hashes, and authenticated encrypted replacement-token material. It contains no
workspace ID, source, decision, run, event, UI payload, raw idempotency key, or
other raw user-authored content. Receipt lookup, expiry, hash comparison,
ciphertext/AAD substitution, inability to recover the revoked workspace, and
inability of the receipt itself to authorize workspace context are negative-test
obligations.

### Data and migration

No deployed feature-001 domain tables or stored user data exist before T009, so
there is no stored-data migration. Alembic migration
`0001_walking_skeleton` will create the clarified schema directly. Future
migrations must preserve explicit workspace scope on workspace-owned rows and
the receipt's non-cascading ten-minute lifetime.

### Evaluation

No numerical quality threshold or dataset changes. T008–T009 migration/model
tests cover scoped candidate keys, child foreign keys, deletion survival,
expiry, content minimization, exact bytes, and authenticated-encryption
substitution. T012 and T020–T021 retain reset authorization and randomized
workspace-isolation coverage.

## Alternatives considered

1. Put `workspace_id` on the replay receipt. Rejected because the receipt is not
   workspace-owned, must outlive deletion of the old overlay, and must not offer
   another identifier from which application code could reconstruct revoked
   context.
2. Keep scope only on aggregate parents. Rejected because the binding
   constitution and accepted architecture require explicit scope on every
   workspace-owned durable row and event.
3. Delete reset replay with the old workspace. Rejected because a lost first
   reset response would become unrecoverable and violate the exact-replay
   acceptance scenario.

## Decision and approval

Accept the bounded operational-receipt exception, Constitution `2.0.0`, the
explicit child-row workspace scope, and replacement baseline `IB-002`.

The amendment replaces an absolute privacy/scope rule with a narrowly bounded
exception. Under the constitution's own semantic-versioning policy this is a
backward-incompatible privacy amendment and therefore requires a major version,
not an editorial patch.

Human approval is recorded by the project owner's instruction in this task to
implement the accepted Whystack roadmap, resolve every critical cross-artifact
finding before application work, preserve exact reset replay and server-derived
workspace scope, and continue after the repair. No automated agent broadened
the product or lowered a quality threshold.

## Replacement artifacts and hashes

| Artifact | Version or role | SHA-256 |
|---|---|---|
| `.ai-sdlc/baselines/IB-001.yaml` | immutable superseded manifest | `2246de84131c55fcc0b16d16913c5c3d0d41233a5e31bd002680ef21d97e2580` |
| `.specify/memory/constitution.md` | `2.0.0` | `379f542f1a929430246c86e98c7be304f8f37969d18ad49a3e0be0b48dd96767` |
| `_bmad-output/planning-artifacts/prd.md` | clarified `NFR-002` | `a9d5fa2e49521957da1325aa81645d50ac41b8717a497eed681f0f3c9147406e` |
| `_bmad-output/project-context.md` | `IB-002` context | `384b41a84878a84bfe2298bbbb6185f8ea227a33714056e0196f208f4ecd0c1c` |
| `_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md` | `IB-002` architecture | `cff115d33a6aa1b15720b30eb44eff0a97d77ee7dd60350ca45559418d7d0c54` |
| `_bmad-output/planning-artifacts/implementation-readiness.md` | `IB-002` readiness `PASS` | `ce43fd35d2aaaf09d5f86e282e362fb71020b46b6e4147b7467cb802ec2ff6d3` |
| `_bmad-output/test-artifacts/system-test-design.md` | `IB-002` security coverage | `99f6a829a8001f11a7c728950b1afb673471090e06fbba350318bef8828eedba` |

The active manifest at `.ai-sdlc/inception-baseline.yaml` is issued as
`IB-002`; it records the hashes of every authoritative artifact, including this
change request, and supersedes rather than edits the archived `IB-001` manifest.

## Spec Kit disposition

- Amend `001-walking-skeleton` data model, plan, tasks, constitution reference,
  and traceability before T008.
- Rerun bootstrap and cross-artifact analysis.
- Stop T008–T009 if any critical or high inconsistency remains.
- No feature is stopped or newly created by this clarification.
