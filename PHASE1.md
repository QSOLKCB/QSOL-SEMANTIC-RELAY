# Phase 1: Apparatus Validation and Paired Analysis

Phase 1 does not introduce a harder semantic task. It turns the Phase 0 harness into a self-auditing evidence pipeline for repeated Experiment 001 runs.

## Run contract

A Phase 1 CLI run publishes only after all requested replications succeed. Every result row additionally records:

- `schema = qsol.semantic-relay.result.v1`;
- one run UUID shared by the complete invocation;
- the requested replication count;
- the base seed used to derive condition and order seeds.

These fields let downstream validation distinguish a complete declared run from an arbitrary prefix or a mixture of invocations.

## Independent validation

`python -m semantic_relay.analyze` rejects a result artifact unless it can verify:

- one coherent run identity and experiment identity;
- exactly four records per requested replication;
- contiguous replication indices;
- unique replication UUIDs;
- exactly one of each control condition per replication;
- deterministic condition execution order from the base seed;
- deterministic condition seeds;
- exact reconstruction of each reader board from the writer board;
- all recorded board and output SHA-256 hashes;
- exact-answer scoring;
- writer word-budget compliance;
- timezone-bearing replication timestamps.

When `--experiment` is supplied, the analyzer also verifies the recorded experiment-input hash, expected answer, experiment ID, and writer word budget against the frozen fixture.

## Descriptive summary only

The analyzer reports:

- accuracy for each condition;
- `REAL - NULL`, `REAL - SHUFFLED`, and `REAL - RANDOM` accuracy differences;
- paired counts for real-only correct, control-only correct, both correct, and both wrong.

Phase 1 deliberately does **not** choose a significance test. Statistical inference belongs in a later protocol only after the apparatus has produced enough valid real-model runs to justify predeclaring one.

## Example

Run the frozen relay experiment:

```bash
PYTHONPATH=src python -m semantic_relay.runner \
  --experiment experiments/001-relay.json \
  --writer-cmd "ollama run qwen2.5:3b" \
  --reader-cmd "ollama run qwen2.5:3b" \
  --replicates 20 \
  --seed 1729 \
  --output results/exp001-qwen25-3b.jsonl
```

Validate and summarize it:

```bash
PYTHONPATH=src python -m semantic_relay.analyze \
  --input results/exp001-qwen25-3b.jsonl \
  --experiment experiments/001-relay.json \
  --output results/exp001-qwen25-3b.analysis.json
```

The raw JSONL remains the primary evidence artifact. The analysis JSON is a deterministic validation-and-summary product bound to the raw file by SHA-256.
