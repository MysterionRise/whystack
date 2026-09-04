---
artifact: product-brief
baseline: IB-002
status: accepted
date: 2026-07-27
---

# Product Brief: AI CTO Cockpit

## Product thesis

Architecture decisions in small AI teams are often made through fragmented
browser research, chat transcripts, issue comments, and intuition. The final
choice loses its evidence, rejected alternatives, constraints, and later
learning. Generic assistants can produce polished answers, but they rarely
expose whether the answer satisfies a hard constraint, which source revision
supports a claim, or which remembered preference changed a ranking.

AI CTO Cockpit turns this activity into a persistent, inspectable decision
workspace. It combines cited retrieval, deterministic constraint enforcement
and ranking, a controlled generative interface, and user-governed long-term
memory.

## Primary user

The primary user is a technical founder or hands-on engineering leader at an
early-stage AI company:

- responsible for architecture without a full platform or research staff;
- balancing delivery speed, cost, operational capacity, privacy, and lock-in;
- working from repositories, product notes, issue history, and public sources;
- willing to use remote models when data-egress boundaries are explicit;
- needs a defendable recommendation and ADR, not a long conversational essay.

Secondary observers are recruiters, clients, and engineering peers evaluating
the project as a portfolio artifact. Their goal is to inspect the quality of
the product thinking, architecture, AI evaluation, and delivery process.

## User job and pains

**Core job:** Given my project evidence, explicit constraints, and relevant
accepted decisions, help me select a viable architecture and leave an audit
trail that I can inspect, correct, and export.

Current pains:

- evidence is spread across files, code, GitHub, and web pages;
- chat answers blur facts, assumptions, and unsupported claims;
- “preferences” are remembered opaquely or not at all;
- scoring criteria change between alternatives;
- decisions are difficult to revisit when evidence changes;
- teams cannot tell whether an assistant improved or merely sounded confident.

## Desired outcome

Within a fifteen-minute portfolio session, a visitor can understand the project,
complete two related decisions, inspect the evidence and constraints behind each
recommendation, control what becomes memory, and see an explained change in the
second ranking. An exported ADR remains useful without the application.

For a local user, the same workflow operates on real read-only sources while
keeping canonical data in local stores and clearly disclosing remote inference.

## Differentiation

AI CTO Cockpit is not differentiated by a novel chat box. It demonstrates five
coupled capabilities:

1. **Evidence discipline:** immutable source revisions, resolvable citations,
   evidence coverage, and abstention.
2. **Decision discipline:** typed constraints and deterministic scoring separate
   model judgment from application authority.
3. **Memory discipline:** explicit facts are durable; inferences require
   confirmation; every influence is visible and reversible.
4. **Interface discipline:** the model selects data for reviewed decision
   components; React retains rendering and action authority.
5. **Engineering discipline:** versioned contracts, replayable runs, observable
   quality, cost budgets, and a traceable BMAD-to-Spec Kit lifecycle.

## Product approaches considered

### A. Conversational research assistant

A chat interface with retrieval and citations would be quickest to build, but
it would hide decision structure, make comparison unstable, and underrepresent
the Generative UI and memory thesis. Rejected for the flagship.

### B. Persistent controlled decision workspace

A structured workspace with bounded adaptive components, explicit outcomes, and
inspectable memory provides the strongest demonstration while keeping authority
deterministic. Selected for version one.

### C. Autonomous virtual CTO

An agent that changes repositories, issues, or infrastructure would be visually
compelling but expands authorization, safety, evaluation, and operational risk
beyond the portfolio objective. Rejected for version one.

## Version-one capability

Version one will:

- expose server-enforced public-demo and local-data profiles;
- ingest and revision permitted evidence sources;
- create versioned decision frames with weighted criteria and typed constraints;
- retrieve, rerank, cite, assess, score, recommend, present a close call, or
  abstain;
- stream controlled decision components and replay interrupted runs;
- record explicit decision outcomes;
- propose, confirm, correct, supersede, and delete durable memory;
- explain memory influences on later recommendations;
- export Markdown ADR and machine-readable JSON;
- expose evaluation and trace metadata without leaking private content;
- provide an original two-decision public corpus and read-only local connectors.

## Explicit non-goals

- team accounts, invitations, comments, or collaborative editing;
- general product-roadmap prioritization;
- repository, GitHub, deployment, purchasing, or messaging writes;
- autonomous implementation or approval;
- arbitrary model-generated HTML, JavaScript, routes, or actions;
- fully offline inference;
- OCR-heavy or media-first ingestion;
- enterprise identity, compliance certification, or regional hosting;
- redistribution of course notebooks, lab assets, or unclear-license material.

## Modes and privacy promise

The public demo uses a fixed synthetic corpus and ephemeral guest overlay.
Uploads and live connectors are rejected at the API boundary. A visitor can
reset their overlay, and it expires after 24 hours.

Local-data mode persists user material locally and permits read-only connectors.
Selected context may leave the machine for remote inference. The product must
state this accurately before connector activation and before the first model
run. It must never market local storage as fully private inference.

## Success measures

Product success for the first public release requires:

- the canonical two-decision journey completes without operator intervention;
- at least 80% of five moderated target users can explain the recommendation,
  its most important evidence, and its memory influence after one session;
- at least 80% can correct or delete a memory without documentation;
- all blocking thresholds in `ai-quality-contract.md` pass;
- a clean repository clone can start the seeded experience using the documented
  container workflow;
- the portfolio documentation lets a reviewer trace a visible behavior to its
  requirement, feature, test, and evaluation.

## Principal hypotheses

| Hypothesis | Evidence required |
|---|---|
| Structured comparison creates more trust than free-form chat | Moderated users correctly identify evidence, constraint, and uncertainty states |
| Explained memory creates value without feeling invasive | Users understand and successfully correct the memory influence |
| Deterministic scoring reduces recommendation drift | Paraphrase-stability and hard-constraint evaluation gates pass |
| A synthetic corpus can still demonstrate authentic complexity | Users complete the journey and recognize realistic trade-offs |
| Bounded generative UI feels adaptive without surrendering control | Users use comparison/evidence components and UI schema tests fail closed |

## Principal risks

- A polished interface could disguise weak retrieval. Mitigation: visible
  evidence coverage and blocking retrieval/citation gates.
- The memory story could feel fabricated. Mitigation: two connected decisions,
  explicit events, and an inspectable influence ledger.
- Public model usage could create abuse cost. Mitigation: fixed corpus, bounded
  context/steps, signed guest scope, quotas, concurrency limits, and spend stop.
- “Local” language could mislead users. Mitigation: explicit storage versus
  inference disclosure and disabled-by-default connectors.
- Framework ceremony could dominate delivery. Mitigation: BMAD stops at
  readiness and Spec Kit is the only implementation loop.
