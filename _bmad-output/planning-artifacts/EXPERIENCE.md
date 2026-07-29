---
artifact: experience-contract
baseline: IB-001
status: accepted
date: 2026-07-27
---

# Experience Contract

## Information architecture

The application has five stable destinations:

1. **Decisions:** workspace overview and decision history.
2. **Sources:** corpus, revision, provenance, sync, and deletion state.
3. **Memory:** active facts, inactive proposals, superseded facts, and source
   outcomes.
4. **Evaluations:** release quality, run versions, latency, cost, and trace
   metadata.
5. **Settings:** deployment mode, disclosure, connectors, provider status,
   retention, reset, and wipe controls.

A decision detail view contains five ordered stages:

1. Frame
2. Evidence
3. Compare
4. Decide
5. Revisit

The user may return to an earlier stage. Editing the accepted frame after a run
creates a new revision and never rewrites the completed run.

## First-run experience

### Public demo

The landing view identifies the synthetic project, explains that no visitor
files are accepted, and offers “Start the guided decision.” A compact source
manifest shows the fictional project brief, constraints, repository snapshot,
GitHub-style discussions, and dated web snapshots.

The mode badge is always visible. The visitor does not configure credentials.
The system creates a signed guest workspace and shows the 24-hour expiry and
reset behavior before the first outcome.

### Local-data mode

The first-run screen separates three facts:

- source files, canonical records, and vectors remain in local services;
- selected retrieved passages are sent to the configured remote inference
  provider;
- connector credentials remain server-side.

The user acknowledges this disclosure before enabling connectors. Provider and
connector readiness are tested without exposing credentials. A failed test
leaves the connector disabled and provides a safe diagnosis.

## Canonical public journey

### 1. Orient

The visitor sees a prepared fictional AI startup and the first architecture
decision. The interface provides a six-step tour that highlights the decision
frame, source manifest, hard constraints, evidence inspector, outcome controls,
and memory ledger. The tour can be dismissed and restarted.

Success: the visitor can state what decision is being made and that the corpus
is synthetic.

### 2. Frame

The user reviews:

- a one-sentence decision question;
- relevant project context;
- three candidate alternatives;
- weighted criteria;
- typed hard constraints;
- advisory guidance.

Changing a criterion previews normalized weights. Removing or weakening a hard
constraint requires an explicit confirmation that describes its effect. The
system validates the frame before enabling a run.

Success: the accepted frame has at least two options, one weighted criterion,
and no invalid constraint.

### 3. Retrieve and assess

The run view presents truthful stages: framing query, retrieving, reranking,
checking constraints, assessing criteria, validating citations, scoring, and
preparing the decision surface.

The first useful UI appears as soon as valid evidence or a meaningful blocking
state is available. The user may inspect source excerpts while later stages
continue. Closing or reconnecting does not create a second run.

Success: the user can identify which sources were considered and whether
coverage is sufficient.

### 4. Compare

The comparison keeps criteria in the user’s chosen order. Each option shows:

- hard-constraint status;
- criterion assessment and deterministic weighted score;
- cited supporting and conflicting evidence;
- risks and unknowns;
- evidence coverage.

Selecting a citation opens the evidence inspector at the immutable revision and
locator. The user can distinguish model assessment from deterministic score.

Success: the user can explain why the leading alternative leads and what could
invalidate it.

### 5. Decide

The result is one of:

- **Recommendation:** coverage is at least 70%, the leading viable option has a
  score lead of at least five points, and citations validate.
- **Close call:** multiple viable options remain within five points.
- **Abstention:** a hard constraint is unknown, evidence coverage is below 70%,
  no option is viable, or citation repair fails.

For a recommendation, the user can accept, edit-and-accept, dismiss, or defer.
The confirmation summarizes exactly what will be recorded. A close call can be
accepted only after the user selects and explains an option. An abstention
cannot be relabelled as a recommendation; the user can revise the frame or add
evidence.

Success: an explicit outcome event links to the exact frame and run revisions.

### 6. Remember

An accepted decision creates a proposed memory summary. Facts directly stated
by the outcome can be active immediately and are labelled “from your accepted
decision.” Any broader preference inferred from behavior remains inactive.

The user can:

- inspect the typed value and source event;
- confirm or reject an inferred proposal;
- correct an active fact, creating a superseding fact;
- delete a fact;
- see which past and current runs used it.

Success: the user understands the difference between explicit fact and inferred
proposal and can reverse either.

### 7. Revisit

The visitor opens the prepared related decision. Before running it, the context
preview lists applicable memory by priority. After the run, `DecisionDelta`
shows whether the ranking changed because of:

- changed evidence;
- changed frame or criterion weights;
- changed constraints;
- deterministic scoring;
- memory influence.

The explanation links each memory influence to its source outcome and displays
the score delta it caused. An unrelated fact must not appear.

Success: the visitor can say why the result changed without trusting an opaque
“personalized” label.

### 8. Export

After acceptance, the user downloads a Markdown ADR and JSON bundle. A preview
shows the question, alternatives, decision, evidence, constraints, risks,
unknowns, memory influences, and version fingerprints.

Success: the Markdown ADR is understandable without the application and every
available citation locator remains identifiable.

## Local source journey

### Configure

The user adds an allowlisted local repository path, uploads a supported
document, supplies a read-only GitHub token, or enters an allowed public web
source. Each connector names the data it reads, where it sends content, and how
to disconnect and wipe it.

### Synchronize

The source list shows discovered items, active revisions, parser state, index
state, last successful cursor, retry state, and tombstones. Long operations can
be left and resumed. A failed artifact does not invalidate successful siblings.

### Inspect

The user can view origin, checksum, parser version, observed time, revision
history, active citation count, and deletion state. Raw secrets or hidden
repository paths are not displayed in shareable traces.

### Disconnect and delete

Disconnect prevents future sync but retains canonical evidence until deletion.
Delete explains its effect on active search, historical decisions, citations,
derived vectors, and audit metadata. Completion is visible, and reconciliation
must finish within the quality limit.

## Generative UI authority

The model may select a reviewed component kind and supply schema-valid data. It
may not:

- place components outside the current workflow region;
- invent navigation or actions;
- submit forms or commit state;
- emit executable markup or code;
- alter labels for consequential actions;
- hide hard-constraint, evidence-coverage, or abstention status.

React decides layout, responsive transformation, accessibility semantics,
action handling, confirmations, and error recovery. Unknown envelopes become a
safe typed error; raw payload content is not rendered.

## Memory interaction policy

- Active explicit facts are distinguished from confirmed inferred preferences.
- Inactive proposals never affect retrieval, ranking, or display ordering.
- A context preview shows which facts a run will receive.
- Facts are organized by decision, constraint, preference, and working context.
- Each fact shows provenance, creation time, validity, last use, and
  supersession.
- Conflict resolution priority is current frame, typed constraints, recent
  accepted outcomes, explicit preferences, confirmed inferred preferences, then
  older history.
- If two facts at the same priority conflict, neither silently wins; the run
  surfaces the conflict for correction.

## Error and recovery experience

### Provider unavailable

Preserve the frame and retrieved evidence. State that assessment did not
complete, expose no provisional recommendation, and offer an idempotent retry.

### Retrieval unavailable

Keep canonical decisions and exports readable. Disable new recommendation runs,
identify the index dependency, and provide reconciliation status.

### Citation invalid

Show “citation validation failed,” not the unverified recommendation. Permit one
automatic repair, then offer frame revision or retry after source inspection.

### Stale edit

Show the newer revision and a field-level comparison. Do not automatically
merge constraints or outcomes.

### Stream interruption

Reconnect from the last acknowledged cursor. If replay is unavailable, mark the
run interrupted and let the user start a new run; never imply completion.

### Permission denial

Name the unavailable capability and current mode. Do not suggest that a prompt
or UI workaround can bypass it.

### Daily spend ceiling

Preserve all non-generation functionality and clearly state that new runs are
paused until the configured reset or administrator action.

## Accessibility flow requirements

- Each stage has one page heading and a labelled status.
- Keyboard order follows frame, result, evidence, then actions.
- Opening a citation moves focus to the inspector heading; closing returns to
  the citation.
- Stream announcements occur on stage or component completion, not each token.
- Comparison has equivalent semantic relationships in table and stacked forms.
- Error summaries link to the affected field.
- Charts include a concise text conclusion and accessible data table.
- Destructive memory and source deletion has clear scope, confirmation, and
  completion feedback.

## Moderated usability acceptance

Five target users receive only the product landing page. At least four must,
without facilitator correction:

- complete both decisions;
- identify one hard constraint and one supporting citation;
- explain whether the second ranking changed and why;
- correct or delete a memory;
- distinguish local storage from remote inference;
- find the ADR export.

Observed confusion is classified as copy, interaction, information-architecture,
or product-model failure and routed to the appropriate baseline or feature
change.

