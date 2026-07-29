# Fresh-Repository Bootstrap Prompt

Paste the block below into the first coding task after copying this packet into
its standalone repository.

> Build only the first verified slice of AI CTO Cockpit feature
> `001-walking-skeleton`.
>
> Treat the repository files as the authority. First read `AGENTS.md`,
> `.ai-sdlc/WORKFLOW.md`, `.ai-sdlc/inception-baseline.yaml`,
> `_bmad-output/project-context.md`, `.specify/memory/constitution.md`, and every
> artifact under `specs/001-walking-skeleton/`.
>
> Before editing, inspect `git status` and run
> `./scripts/verify-bootstrap.sh`. If it fails, diagnose and repair the packet
> without writing application behavior.
>
> Use Spec Kit as the only feature-delivery loop. Run `speckit-analyze` (or
> perform its repository-local equivalent) across the active specification,
> plan, contracts, tasks, constitution, and BMAD traceability. Resolve every
> critical inconsistency before implementation. Do not invoke BMAD story,
> sprint, quick-development, automated-development, or implementation-review
> workflows.
>
> Invoke `speckit-implement` (or the integration-equivalent Spec Kit command)
> with the explicit instruction to execute exactly tasks T001 through T003
> from `specs/001-walking-skeleton/tasks.md` and stop:
>
> 1. Complete T001 reproducible workspace manifests and locked tooling.
> 2. Write and run the T002 Compose-readiness acceptance test. Preserve the
>    command and expected failure proving the topology is absent.
> 3. Implement only the T003 process skeleton needed to make T002 pass.
> 4. Refactor only while the same tests remain green.
>
> Do not add retrieval, model-provider calls, recommendation logic, long-term
> memory, live connectors, arbitrary generated UI, or any later task. Preserve
> PostgreSQL as canonical state, Qdrant as derived state, server-derived
> workspace scope, and the public-demo capability boundary.
>
> Before claiming completion, run the bootstrap verifier plus every verification
> command named by T001–T003. Report the initial RED evidence, final GREEN
> evidence, files changed, remaining risks, and the next unstarted task. Do not
> weaken tests or accepted quality thresholds to obtain a pass.

After T001–T003 are reviewed and committed, start a new bounded task for the
next RED→GREEN pair. A cross-cutting discovery must follow the baseline-change
path in `.ai-sdlc/WORKFLOW.md`; it must not be smuggled into a feature task.
