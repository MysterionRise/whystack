# Provenance and Clean-Room Policy

## Purpose

The bootstrap packet must be independently publishable. It can reuse architectural
insights learned from courses, documentation, and experiments, but it cannot copy
restricted notebooks, lab assets, private repositories, credentials, or unattributed
third-party text.

## Fixture Provenance

Everything under `seed/sample-project/` is original synthetic material created for AI CTO
Cockpit. Northstar Relay, AtlasVector, NimbusVector, SearchBox, StreamForge, ManagedTasks,
their people, incidents, discussions, pull requests, benchmarks, and prices are fictional.
Names of established open-source technologies such as PostgreSQL, Qdrant, FastAPI, React,
and Docker are used descriptively; fixture performance and costs are not claims about those
projects or current service commitments.

The two web snapshots are deliberately vendor-neutral fictional captures. They exist to
exercise dated-source retrieval, citation, conflicting evidence, and prompt-injection
defenses. They must not be presented to users as current external facts.

The fixture is distributed under the same MIT license as the bootstrap packet. Its
`manifest.yaml` records stable artifact IDs, paths, source kinds, dates, and licenses.
Ingestion calculates content checksums; committed hashes are not required for authored
fixtures because line-oriented edits during planning would make them misleading.

## Course-Derived Insights

An insight may enter this project when all of the following are true:

1. It is expressed as a general engineering principle rather than copied expression.
2. Project-owned prose, examples, code, data, and tests are written independently.
3. Its source course and local commit are recorded in the course repository's project
   signal, not embedded as a runtime dependency.
4. Any third-party algorithm, interface, or data license is reviewed separately.
5. A reviewer can understand and test the result without access to the course material.

## External Source Capture

Local-data mode records:

- Original and final URL.
- Retrieval time and declared publication/update time when available.
- Media type, title, checksum, and parser version.
- Exact evidence locator and immutable extracted revision.
- Workspace scope and deletion status.

Web content remains copyrighted by its owner and is not redistributed in the public seed.
Only short, purpose-limited excerpts are supplied to a model or displayed as citations.

## Models, Prompts, and Evaluations

Every evaluated run records model/provider identifier, model parameters, prompt-template
version, schema version, retrieval and reranker versions, dataset hash, application
commit, latency, token counts, and cost estimate. Human labels record the rubric version
and reviewer identifier. A score without this run manifest is exploratory, not a release
result.

## Contribution Review

Contributors must identify the origin and license of new fixtures. Generated content must
be reviewed for accidental reproduction, personal data, secrets, and misleading real-world
claims. Pull requests adding binaries, externally captured pages, course materials, or
unclear-license content are rejected until provenance is resolved.
