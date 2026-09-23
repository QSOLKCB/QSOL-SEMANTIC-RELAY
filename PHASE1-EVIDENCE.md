# Phase 1 Evidence Retention Gate

Phase 2 remains blocked until at least one real local-model Phase 1 run satisfies the roadmap exit criteria. This document defines how that evidence is retained as one verifiable package.

## Evidence manifest

The evidence manifest schema is:

```text
qsol.semantic-relay.evidence.v1
```

A manifest binds:

- run and experiment identity;
- the complete experiment-input SHA-256;
- declared model identifier and optional model digest;
- model runtime version;
- repository commit SHA;
- exact writer and reader command labels from the validated run;
- base seed and requested replication count;
- byte-exact SHA-256 and size of the raw JSONL;
- byte-exact SHA-256 and size of the analyzer JSON;
- byte-exact SHA-256 and size of the experiment fixture.

The tool does not trust an existing analysis summary. Before creating a manifest it reruns the Phase 1 analyzer against the raw JSONL and frozen fixture and requires the supplied analysis JSON to match that freshly recomputed summary exactly.

## Create

After a real local-model run and fixture-backed analysis:

```bash
PYTHONPATH=src python -m semantic_relay.evidence create \
  --input results/exp001-qwen25-3b.jsonl \
  --analysis results/exp001-qwen25-3b.analysis.json \
  --experiment experiments/001-relay.json \
  --model-id "qwen2.5:3b" \
  --runtime-version "ollama <version>" \
  --repository-commit "<40-hex-commit>" \
  --output results/exp001-qwen25-3b.evidence.json
```

When the runtime exposes a stable model digest, also provide:

```text
--model-digest "<runtime-specific digest>"
```

## Verify

At any later point, after downloading or restoring the three evidence artifacts:

```bash
PYTHONPATH=src python -m semantic_relay.evidence verify \
  --manifest results/exp001-qwen25-3b.evidence.json \
  --input results/exp001-qwen25-3b.jsonl \
  --analysis results/exp001-qwen25-3b.analysis.json \
  --experiment experiments/001-relay.json
```

Verification re-runs the fixture-backed analyzer, checks the raw and analysis bytes, and reconstructs the expected manifest from the retained metadata.

## Phase 2 gate

A merge of this tooling does **not** itself unlock Phase 2.

The roadmap gate is satisfied only after at least one actual model run has:

1. a valid raw JSONL artifact;
2. a fixture-backed analyzer JSON;
3. an evidence manifest created by this tool;
4. the three artifacts retained together in a durable publication/archive location.

Only then should the roadmap status move from Phase 1 to Phase 2 semantic compression.
