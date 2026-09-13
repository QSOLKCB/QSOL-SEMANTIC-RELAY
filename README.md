# QSOL-SEMANTIC-RELAY

Minimal research repository for testing whether task-relevant semantic state can pass between **context-isolated language-model agents** through a persistent external artifact.

> Can semantic state persist between independently instantiated agents when the only shared state is an external writable artifact?

This repository intentionally starts small. Phase 0 contains one falsifiable experiment, four controls, a standard-library-only Python harness, fresh subprocess agent invocations, synthetic fixtures, hashes, and tests.

## Phase 0 hypothesis

Let `W` be a persistent board artifact. A writer agent observes synthetic facts and writes a compact state to `W`. Its conversational context is then discarded. A fresh reader agent receives only a transformed version of `W` plus a question.

The first effect of interest is:

```text
Delta = P(correct | REAL) - P(correct | NULL)
```

A stronger sanity pattern is:

```text
REAL > NULL ~= SHUFFLED ~= RANDOM
```

This would support a deliberately narrow claim: persistent external symbolic state can mediate measurable semantic transfer between context-isolated agents.

It would **not** by itself establish consciousness, collective agency, or emergent social organisation.

## Controls

| Condition | Reader receives |
| --- | --- |
| `REAL` | Writer's compact board |
| `NULL` | Empty board |
| `SHUFFLED` | Same board tokens in deterministic random order |
| `RANDOM` | Equal token count of deterministic synthetic noise |

All four reader conditions in a replication are derived from the **same writer output**, making the comparison paired.

## Run locally

Requires Python 3.11+ and an agent command that reads a prompt from stdin and writes its response to stdout.

Run the self-tests:

```bash
python -m unittest discover -s tests -v
```

Run Experiment 001 with a small local Ollama model:

```bash
PYTHONPATH=src python -m semantic_relay.runner \
  --experiment experiments/001-relay.json \
  --writer-cmd "ollama run qwen2.5:3b" \
  --reader-cmd "ollama run qwen2.5:3b" \
  --replicates 10 \
  --output results/exp001.jsonl
```

Each invocation is a new subprocess. The model server may remain loaded, but no chat transcript, KV cache, or application conversation state is passed from writer to reader by this harness.

## Recorded provenance

Each JSONL record includes:

- experiment and replication identifiers;
- condition and deterministic seed;
- writer and reader command labels;
- writer-board and reader-board SHA-256 hashes;
- reader-output SHA-256 hash;
- expected and observed answer;
- correctness;
- UTC timestamp.

The board text is also recorded for auditability because the synthetic fixtures contain no private data.

## Scope discipline

Phase 0 deliberately has:

- no database;
- no vector store;
- no web UI;
- no LangChain or multi-agent framework;
- no distributed scheduler;
- no Kubernetes. Absolutely no fucking Kubernetes. :-)

See [`PROTOCOL.md`](PROTOCOL.md) for the experimental contract.
