# Northstar Relay Project Brief

Northstar Relay is a fictional early-stage company building an incident-intelligence
assistant for small European software teams.

The first paid pilot starts on 2026-10-01. The product must summarize incident timelines,
surface similar historical incidents, and draft a post-incident review for human approval.

The pilot targets five customer workspaces and no more than twenty concurrent users. A
useful evidence-backed answer should begin rendering within four seconds and finish within
fifteen seconds at p95.

The company has four engineers. Nobody is assigned as a full-time infrastructure
specialist, so operational simplicity and recoverability are weighted more heavily than
novel technology.

The pilot budget for application infrastructure and managed data services is capped at
GBP 400 per month, excluding model inference.

Customer incident text may contain personal and security-sensitive information. It must
remain in the EU, must not be used to train shared models, and requires deletion within
seven days after a workspace is closed.

The team prefers portable open interfaces and must be able to export accepted architecture
decisions as Markdown. A human remains accountable for every incident conclusion and
consequential action.

