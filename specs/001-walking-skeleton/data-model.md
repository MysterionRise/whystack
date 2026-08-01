# Data Model: Walking Skeleton

Baseline: IB-002
Feature: 001  
Canonical store: PostgreSQL

## Conventions

- Identifiers are server-generated, canonical lowercase UUIDv7 values.
- Database timestamps are timezone-aware UTC.
- Durable rows include `created_at`; mutable control rows also include
  `updated_at`. The immutable `DeletionCompletion` uses its database-supplied
  `completed_at` as its creation timestamp because the row is created only when
  deletion commits.
- Workspace scope is present on top-level aggregate and job records and is
  derived from trusted server context.
- JSON columns store a validated, versioned document plus its SHA-256 canonical
  serialization hash where replay or comparison matters.
- API names use lower camel case. Database names use snake case.

## Enumerations

### DeploymentMode

- `public-demo`
- `local-data`

### WorkspaceKind

- `seed`: immutable bundled corpus.
- `guest`: expiring overlay whose `seed_parent_id` identifies the visible seed.
- `local`: persistent local-data workspace.

### WorkspaceStatus

- `active`
- `deleting`
- `deleted`

### RunStatus

- `queued`
- `running`
- `completed`
- `failed`

### RunEventKind

- `run.queued`
- `run.started`
- `ui.envelope`
- `run.completed`
- `run.failed`

### JobKind

- `execute-run`
- `delete-workspace`

### JobStatus

- `available`
- `leased`
- `completed`
- `failed`

## Durable entities

### Workspace

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key; never returned to browser clients |
| `kind` | WorkspaceKind | Immutable |
| `status` | WorkspaceStatus | Defaults to `active` |
| `seed_parent_id` | UUID or null | Required only for `guest`; references a `seed` workspace |
| `expires_at` | timestamp or null | Required for `guest`; exactly 24 hours after session creation |
| `created_at` | timestamp | Database supplied |
| `updated_at` | timestamp | Database supplied |

Invariants:

- A `seed` workspace has no parent and no expiry.
- A `guest` workspace has one seed parent and an expiry.
- A `local` workspace has no seed parent and no expiry.
- `deleted` workspaces are inaccessible to application queries.

### GuestSession

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Unique; references a guest workspace |
| `token_hash` | bytes | Unique one-way hash; raw token is never stored |
| `expires_at` | timestamp | Matches workspace expiry |
| `revoked_at` | timestamp or null | Non-null immediately after reset |
| `created_at` | timestamp | Database supplied |

The signed cookie contains an opaque session identifier and integrity
protection. Lookup compares hashes in constant time. Expired or revoked sessions
cannot derive the old workspace context. The sole exception is the reset route's
short-lived replay branch: it may cryptographically verify a revoked cookie and
use its one-way fingerprint to find an unexpired `ResetReplayReceipt`; it never
restores the old workspace context.

### Decision

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Indexed scope; references an active workspace |
| `current_revision` | integer | Positive; begins at 1 |
| `created_at` | timestamp | Database supplied |
| `updated_at` | timestamp | Changes only when a revision is appended |

Unique and access rule: every read or mutation selects by both `id` and the
server-derived `workspace_id`. The database also declares
`UNIQUE (workspace_id, id)` as the candidate key for scoped child references.

### DecisionRevision

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Indexed server-derived scope; must match the parent Decision workspace |
| `decision_id` | UUID | References Decision |
| `revision` | integer | Positive and unique per decision |
| `frame_schema_version` | string | `1.0` for this feature |
| `question` | string | 1–500 Unicode characters after trimming |
| `context` | string | 0–10,000 Unicode characters |
| `options` | JSON array | 2–8 `DecisionOption` objects with unique IDs |
| `criteria` | JSON array | 1–10 `Criterion` objects; exact entered decimal strings are preserved and normalized strings sum to `100.0000` |
| `constraints` | JSON array | 0–20 typed `Constraint` objects |
| `snapshot_hash` | string | Lowercase SHA-256 hex of canonical frame |
| `created_at` | timestamp | Database supplied |

Decision revisions are append-only. The database unique constraint is
`(decision_id, revision)`. A composite foreign key
`(workspace_id, decision_id)` references the parent Decision's matching
workspace-scoped identity. The database also declares
`UNIQUE (workspace_id, decision_id, id)` as the candidate key that prevents a
Run from pairing one Decision with another Decision's revision. Application
reads include the server-derived workspace column.

### Run

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Indexed scope |
| `decision_id` | UUID | References Decision |
| `decision_revision_id` | UUID | References immutable DecisionRevision |
| `status` | RunStatus | Monotonic transition |
| `fixture_version` | string | `walking-skeleton-v1` |
| `input_snapshot` | JSON object | Exact validated frame used by the run |
| `input_snapshot_hash` | string | Lowercase SHA-256 hex |
| `last_event_sequence` | integer | Begins at 0 |
| `terminal_event_sequence` | integer or null | Set once on completion or failure |
| `error_code` | string or null | Stable non-secret code for failed runs |
| `created_at` | timestamp | Database supplied |
| `started_at` | timestamp or null | Set once |
| `completed_at` | timestamp or null | Set once for terminal status |

Allowed transitions are `queued → running → completed` and
`queued|running → failed`. Terminal rows cannot transition again.
The composite foreign key
`(workspace_id, decision_id, decision_revision_id)` references
`DecisionRevision (workspace_id, decision_id, id)`, so every Run snapshot is
bound to a revision of its own Decision rather than merely another revision in
the same workspace.
The database declares `UNIQUE (workspace_id, id)` as the candidate key for
scoped RunEvent references.

### RunEvent

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Indexed server-derived scope; must match the parent Run workspace |
| `run_id` | UUID | References Run |
| `sequence` | integer | Begins at 1; unique and contiguous per run |
| `kind` | RunEventKind | Determines payload schema |
| `payload_schema_version` | string | `1.0` |
| `payload` | JSON object | Validated before insertion |
| `payload_hash` | string | Lowercase SHA-256 hex |
| `created_at` | timestamp | Database supplied |

The unique constraint `(run_id, sequence)` and row lock on Run prevent duplicate
sequence allocation. A composite foreign key `(workspace_id, run_id)`
references the parent Run's matching workspace-scoped identity, and application
reads include both columns. `ui.envelope` payloads validate against the
controlled UI schema before insertion.

### Job

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Indexed scope |
| `kind` | JobKind | Determines payload |
| `payload` | JSON object | For `execute-run`, contains only `run_id`; for deletion, only `workspace_id` |
| `status` | JobStatus | Defaults to `available` |
| `available_at` | timestamp | Claim lower bound |
| `lease_owner` | string or null | Worker instance identifier |
| `lease_expires_at` | timestamp or null | Renewable lease boundary |
| `attempt_count` | integer | Non-negative |
| `last_error_code` | string or null | Stable redacted code |
| `created_at` | timestamp | Database supplied |
| `updated_at` | timestamp | Database supplied |
| `completed_at` | timestamp or null | Set once |

A worker claims one job using an ordered `FOR UPDATE SKIP LOCKED` transaction.
An expired leased job becomes claimable. Execution reads durable run state and
must not insert a second terminal event. A `delete-workspace` job is durable and
lease-recoverable until its successful deletion transaction. That transaction
inserts `DeletionCompletion`, marks the attempt successful, and deletes the
workspace atomically. The workspace cascade intentionally removes the
workspace-owned job, while the non-sensitive completion record remains.

### DeletionCompletion

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Server-derived deleted-workspace scope; indexed and deliberately has no foreign key |
| `operation` | string | Constant `delete-guest-workspace-v1` |
| `job_id` | UUID | Unique identifier copied from the completed deletion job; deliberately has no foreign key |
| `completed_at` | timestamp | Database supplied in the successful deletion transaction |

The unique constraints are `(workspace_id, operation)` and `(job_id)`, so a
retry cannot create a second completion record. This audit-only row contains no
workspace payload, source, decision, run, session token, request body, or other
user-authored content. It is never used to authorize or reconstruct a deleted
workspace and is excluded from guest responses and telemetry. It is the
non-sensitive deletion completion record required by `QUALITY-OPS-001`; later
features extend deletion audit state for the data types they introduce without
retaining deleted private content.

### IdempotencyRecord

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `workspace_id` | UUID | Scope |
| `operation` | string | Stable route operation name |
| `key` | string | 8–128 visible ASCII characters |
| `request_hash` | string | SHA-256 of normalized request and relevant headers |
| `response_status` | integer | Original HTTP status |
| `response_body` | JSON object | Original response document |
| `resource_id` | UUID or null | Created aggregate identifier |
| `expires_at` | timestamp | At least guest-workspace lifetime |
| `created_at` | timestamp | Database supplied |

The unique constraint is `(workspace_id, operation, key)`. Same key and request
hash returns the original response. Same key with another hash returns conflict.

### ResetReplayReceipt

This operational receipt is deliberately not owned by or foreign-keyed to a
guest workspace. It is the bounded non-workspace operational-receipt exception
defined by Constitution Article VI: it has no `workspace_id` or raw
user-authored content, cannot derive or restore the triggering or revoked
workspace identity or context, cannot itself authorize a workspace, and is
reachable only through the separately verified one-way old-session fingerprint.
It may reproduce only the already-committed replacement response and credential;
ordinary GuestSession verification on a later request is the only step that
derives replacement workspace context. Deleting the old overlay and its session
therefore cannot destroy the narrow retry capability required after a lost reset
response.

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `old_session_fingerprint` | bytes | One-way fingerprint derived from the verified old cookie; never the raw token |
| `operation` | string | Constant `reset-guest-session-v1` |
| `key_hash` | bytes | Domain-separated SHA-256 of the original 8–128-character idempotency key; raw key is never stored |
| `request_hash` | string | SHA-256 of versioned operation, method, path, query, and canonical body; excludes cookie and idempotency header |
| `replacement_session_id` | UUID | Copied replacement identifier for audit/reconstruction; intentionally has no cascading foreign key |
| `replacement_token_hash` | bytes | Copy of the one-way token hash inserted with the replacement session; used for constant-time post-decrypt verification |
| `replacement_token_ciphertext` | bytes | Authenticated encryption of only the high-entropy replacement token; includes nonce and authentication tag |
| `encryption_key_id` | string | Identifies the authenticated-encryption key retained for at least the receipt lifetime |
| `aad_version` | string | Constant `reset-replay-aad-v1` |
| `cookie_profile_version` | string | `public-demo-v1`; fixes cookie name, serialization, and security attributes |
| `cookie_signing_key_id` | string | Identifies the signing key retained for at least the receipt lifetime |
| `cookie_issued_at` | timestamp | Fixed value used by deterministic cookie signing |
| `cookie_expires_at` | timestamp | Fixed replacement-session expiry used by deterministic cookie signing |
| `response_status` | integer | Constant `202` |
| `response_content_type` | string | Constant `application/json` for v1 |
| `response_serializer_version` | string | `canonical-json-v1` |
| `response_body_bytes` | bytes | Exact serialized bytes sent by the original reset response |
| `response_body_hash` | string | SHA-256 of `response_body_bytes` |
| `expires_at` | timestamp | Exactly ten minutes after original reset commit |
| `created_at` | timestamp | Database supplied by the original reset transaction |

`key_hash` is exactly SHA-256 over the UTF-8 bytes of
`ai-cto-cockpit/reset-replay/idempotency-key/v1`, followed by one NUL byte and
the raw idempotency key. This domain is versioned and must be shared by receipt
insertion and lookup.

The unique constraint is
`(old_session_fingerprint, operation, key_hash)`. On a reset retry, a constant-time
request-hash match returns `response_body_bytes` unchanged and deterministically
recreates the exact original `Set-Cookie` value from the decrypted token and
fixed cookie fields. The route derives the token hash after decryption and
compares it to `replacement_token_hash` in constant time before signing. A
same-key hash mismatch is a conflict. A different key or missing or expired
receipt is unauthorized because the old session remains revoked.

AEAD associated data is the canonical encoding of `id`,
`old_session_fingerprint`, `operation`, `key_hash`, `request_hash`,
`replacement_session_id`, `replacement_token_hash`,
`encryption_key_id`, `aad_version`, `cookie_profile_version`, `cookie_signing_key_id`,
`cookie_issued_at`, `cookie_expires_at`, `response_status`,
`response_content_type`, `response_serializer_version`, `response_body_hash`,
`created_at`, and `expires_at`. Substituting a ciphertext or any bound field
between receipt rows therefore fails authentication. Before replay, the route
also verifies the SHA-256 of `response_body_bytes` against
`response_body_hash`. The original transaction must insert the same replacement
token hash into `GuestSession` and this receipt.

For v1, canonical AAD is UTF-8 RFC 8785 JSON with byte fields encoded as
lowercase hexadecimal and timestamps encoded as UTC RFC 3339 strings with six
fractional digits. `canonical-json-v1` uses the same JSON canonicalization and
timestamp form for the reset response; the resulting bytes are persisted and
replayed directly.

Receipts are purged after expiry independently of workspace deletion. The
ciphertext is decrypted only in the reset replay branch and never logged. A
receipt contains no workspace ID, raw idempotency key, source, decision, run,
event, UI payload, or other raw user-authored content. Its exact response bytes
are server-authored and its encrypted token can only reproduce the
already-committed replacement credential; neither field authorizes a workspace.

## Value objects

### DecisionOption

| Field | Type | Rules |
|---|---|---|
| `id` | string | Lowercase slug, 1–64 characters; unique within frame |
| `label` | string | 1–120 characters |
| `description` | string | 0–1,000 characters |

### Criterion

| Field | Type | Rules |
|---|---|---|
| `id` | string | Lowercase slug; unique within frame |
| `label` | string | 1–120 characters |
| `enteredWeight` | decimal string | Exact submitted lexical value; no sign, exponent, or leading zero; 1–10 integer digits, at most 8 fractional digits, and numeric range `0.00000001`–`9999999999.99999999`; entered values need not sum to 100 |
| `normalizedWeight` | decimal string | Server-computed percentage with exactly four fractional digits; read-only in API views; all values sum exactly to `100.0000` |

Normalization is deterministic largest-remainder apportionment with integer
arithmetic. Validate the bounded lexical form before expanding it, preserve that
exact string, and right-pad fractional digits to the common maximum scale to
obtain positive integer coefficients `w[i]`; let `W = sum(w)`. One unit equals
`0.0001` percentage point. Integer `divmod(w[i] * 1_000_000, W)` gives each
criterion's floor allocation and exact remainder. Allocate the still-unassigned
units in descending remainder order, breaking ties by ascending criterion ID.
Format allocated units divided by `10_000` with exactly four fractional digits.
No floating-point or rounded intermediate participates, so the algorithm is
independent of browser number behavior, input array order, and decimal context.

Example: criteria `alpha`, `beta`, and `gamma` with entered weights `1`, `1`,
and `1` receive `33.3334`, `33.3333`, and `33.3333` respectively; the one
remainder unit goes to `alpha` by the criterion-ID tie-break.

### Constraint

All constraints contain `id`, `kind`, `label`, and `severity`. Severity is
`hard` or `advisory`. Version 1.0 supports:

| Kind | Required value |
|---|---|
| `budget` | ISO 4217 currency and non-negative maximum amount |
| `deadline` | ISO 8601 calendar date |
| `capability` | Required capability slug |
| `forbidden-vendor` | Vendor name |
| `license` | Allowed SPDX license identifiers |
| `residency` | Allowed ISO 3166-1 alpha-2 country codes |
| `deployment-mode` | One or more of `managed`, `self-hosted`, `on-device` |

Feature 001 validates and stores these values but does not assess them.

## Controlled UI document

`UiEnvelope` version `1.0` contains:

- envelope `schemaVersion`;
- a `recommendation-summary` component with stable ID, title,
  `demonstration` status, selected option ID, rationale, option scores,
  disclaimer, and no citations;
- zero or one disabled `view-evidence` action;
- metadata containing run ID, event sequence, deterministic generator label,
  and fixture version.

Unknown fields are invalid at every object boundary.

## API projections

- `RuntimeConfig` omits workspace ID and returns mode, schema version,
  capability flags, and optional guest expiry.
- `DecisionFrameInput` accepts criterion IDs, labels, and bounded lossless
  decimal-string `enteredWeight` values; it never accepts `normalizedWeight`.
- `DecisionView` returns aggregate ID, current revision, timestamps, and a
  `DecisionFrameView` whose criteria include both the preserved
  `enteredWeight` and server-computed `normalizedWeight`.
- `RunView` returns identity, decision reference, status, event watermark,
  fixture version, timestamps, and safe error code.
- `RunEventView` returns run ID, sequence, kind, schema version, payload, and
  timestamp.
- `ApiError` returns stable code, user-safe message, correlation ID, and optional
  field locations.

## Reserved future domain types

The names `SourceArtifact`, `EvidenceRef`, `OptionAssessment`,
`Recommendation`, `DecisionEvent`, `MemoryFact`, and `MemoryProposal` are
reserved by the product baseline. Feature 001 does not persist or expose them.
Their schemas are introduced only by the feature that implements their behavior.
