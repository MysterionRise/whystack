# Vector Storage Options — Fictional Benchmark

- Capture date: 2026-07-15
- Source type: synthetic benchmark snapshot
- Scope: pilot configurations for Northstar Relay

## Qdrant Local

Runs as one container beside the application, stores vectors in the selected EU host, and
exports collections through a documented snapshot format. Estimated incremental pilot
cost is GBP 55 per month. The team operates backups and upgrades.

## AtlasVector Cloud

The pilot tier is a hosted service with EU storage, an open HTTP query API, and collection
export. Estimated pilot cost is GBP 180 per month. The service-level objective in this
snapshot is 99.5 percent.

## NimbusVector Starter

The benchmark could not verify whether canonical payloads and control-plane backups both
remain in the EU. One sales note claimed an EU region, but no dated technical commitment
was available. Estimated pilot cost is GBP 120 per month.

## SearchBox Enterprise

The quoted configuration provides EU storage and export, but its estimated recurring cost
is GBP 720 per month before model inference.

The scenario, hosted vendors, capabilities, and prices in this snapshot are fictional
evaluation data. Qdrant is named only as an open-source deployment option; the stated
configuration and cost are not current product information.
