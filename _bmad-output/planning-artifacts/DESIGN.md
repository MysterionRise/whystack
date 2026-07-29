---
artifact: visual-design-contract
baseline: IB-001
status: accepted
date: 2026-07-27
---

# Visual Design Contract

## Design intent

AI CTO Cockpit should feel like a calm technical instrument: serious enough for
an architecture review, approachable enough for a founder, and transparent
enough that evidence and uncertainty are never mistaken for decoration.

The interface avoids the visual language of a generic chatbot. The primary
object is a decision, not a message. Evidence, alternatives, constraints,
scores, outcomes, and memory have persistent spatial identities.

## Experience attributes

- **Grounded:** citations, dates, source status, and unknowns are visible.
- **Decisive:** the current question, result state, and next user action are
  immediately legible.
- **Inspectable:** every compact summary can expand to its provenance.
- **Calm:** motion, color, and density support analysis rather than urgency.
- **Bounded:** generative content fits a recognizable component vocabulary.

## Visual foundation

### Typography

- Interface and prose use Inter or the system sans-serif fallback.
- Evidence locators, identifiers, scores, and version fingerprints use IBM Plex
  Mono or the system monospace fallback.
- Body copy uses a minimum rendered size of 16 pixels.
- Reading measure is capped near 72 characters for narrative evidence and ADR
  content.
- Headings communicate hierarchy through size and spacing; all-capital text is
  reserved for short status labels.

### Color

The light theme is the primary release theme:

- canvas: warm off-white `#F7F7F3`;
- primary surface: white `#FFFFFF`;
- raised evidence surface: cool gray `#F1F4F5`;
- primary text: ink `#172124`;
- secondary text: slate `#526166`;
- border: `#CBD3D5`;
- action: deep teal `#086B68`;
- action hover: `#075956`;
- positive/pass: forest `#277A4B`;
- caution/unknown: ochre `#9A6508`;
- critical/fail: brick `#B13A32`;
- focus ring: blue `#1769E0`.

Color never carries meaning alone. Status always includes an icon, word, or
shape. All text and controls meet WCAG 2.2 AA contrast.

### Shape, border, and elevation

- Panels use an eight-pixel corner radius; pills are reserved for compact
  filters and statuses.
- Evidence and recommendation boundaries use one-pixel borders.
- Shadows are subtle and limited to overlays or drag elevation.
- Constraint failures use a strong left rule plus text, not a red-tinted panel
  alone.
- A selected alternative is identified by border, icon, and label.

### Spacing and density

Use a four-pixel base spacing unit. The default workspace is information-dense
but not compressed:

- eight pixels inside compact metadata groups;
- twelve to sixteen pixels inside evidence and criterion rows;
- twenty-four pixels between sections;
- thirty-two pixels around page-level groups.

The user can collapse evidence detail, but critical constraint and abstention
states are never collapsed automatically.

## Layout

### Desktop

The principal decision view uses three regions:

1. **Left rail:** workspace name, decisions, sources, memory, evaluations, and
   mode badge.
2. **Main canvas:** decision frame, progress, option comparison, recommendation,
   and outcome controls.
3. **Evidence inspector:** citation content, source revision, locator, freshness,
   retrieval metadata, and related claims.

The evidence inspector may collapse but opens in place when a citation receives
focus. Recommendation actions remain within the main reading flow rather than a
sticky footer that obscures evidence.

### Tablet and mobile

The left rail becomes a labelled navigation drawer. The evidence inspector
becomes a full-height sheet with an explicit close control and focus return.
Comparison tables become stacked option cards while retaining criteria in a
consistent order. No horizontal scrolling is required for the canonical flow.

### Wide screens

The main canvas is capped for readability; extra width benefits the evidence
inspector and comparison view rather than stretching prose.

## Component language

### Stable application components

React-owned navigation and workflow components include:

- mode and egress disclosure;
- source list and sync status;
- decision-frame editor;
- criterion and constraint editor;
- run controls and progress;
- outcome controls;
- memory ledger and proposal review;
- export controls;
- evaluation and trace summary;
- dialogs, toasts, forms, and error boundaries.

### Model-populated controlled components

The versioned UI envelope may populate these reviewed component kinds:

- **EvidenceDigest:** grouped source excerpts and coverage status;
- **OptionComparison:** alternatives by criterion with cited assessments;
- **ConstraintMatrix:** pass, fail, or unknown results with reasons;
- **RecommendationCard:** recommendation, close call, or abstention;
- **RiskRegister:** impact, likelihood, mitigation, and evidence;
- **MissingEvidencePrompt:** unknowns and safe next steps;
- **MemoryInfluence:** facts that affected ranking and their provenance;
- **DecisionDelta:** evidence, frame, constraint, score, and memory changes
  between two runs;
- **RunProgress:** truthful named workflow stages and recoverable status.

The catalog is additive within a schema version. Unknown components, actions,
fields, or incompatible versions fail closed to a plain error component that
does not render the untrusted payload.

## Data-display conventions

- Scores always show their scale, weights, and evidence coverage.
- A score is not shown with more than one decimal place.
- Pass, fail, and unknown are distinct; unknown is never styled as a weak pass.
- Citation markers use stable numbers within a run and show source title,
  revision date, and locator on focus or selection.
- Model judgment is labelled “assessment”; application calculation is labelled
  “score.”
- Version fingerprints are available in an expandable technical details panel.
- Memory-derived effects are labelled and link to the source outcome.
- Deleted-source citations preserve identity and deletion state, not deleted
  private text.

## Interaction states

Every workflow component defines:

- initial and empty state;
- active/loading state with truthful progress;
- partial evidence state;
- degraded dependency state;
- recoverable failure;
- permission denial;
- stale-revision conflict;
- completed state;
- deleted or superseded historical state.

Skeletons reserve layout but never resemble final scores or evidence. Streaming
content cannot move keyboard focus or announce every token. The interface
announces meaningful component and state completion.

## Motion

Motion is functional and short:

- panel transitions complete within 180 milliseconds;
- score or ordering changes use a brief highlight and a textual delta;
- streamed components appear as complete semantic regions, not token animation;
- reduced-motion preference removes non-essential transitions;
- no pulsing, infinite, or attention-seeking animation is used outside a
  labelled progress indicator.

## Accessibility

- All actions are keyboard reachable in logical document order.
- Focus moves into modal or sheet content and returns to its trigger.
- Comparison content has a semantic table on desktop and equivalent labelled
  groups when stacked.
- Charts have textual summaries and data tables.
- Status icons have programmatic labels.
- Errors associate with the relevant field and appear in a summary.
- Run-progress announcements are throttled to meaningful stage changes.
- Target size is at least 24 by 24 CSS pixels, with larger targets for primary
  actions.
- Automated testing must report zero serious or critical violations, and the
  canonical journeys receive manual keyboard and screen-reader review.

## Content voice

Use concise, direct language:

- say “Not enough evidence to recommend” rather than “I’m not sure”;
- say “Blocked by residency constraint” rather than “This may not work”;
- say “Remember because you accepted Decision D-104” rather than “Based on what
  I know about you”;
- separate fact, assessment, unknown, and action;
- avoid anthropomorphic claims about understanding or intent.

## Responsive acceptance

The canonical demo must be usable at 360-pixel, 768-pixel, 1280-pixel, and
1440-pixel viewport widths, at 200% browser zoom, in keyboard-only navigation,
with reduced motion, and with a screen reader on one desktop platform.

