# QSOL-SEMANTIC-RELAY

Minimal research repository for testing whether task-relevant semantic state can pass between **context-isolated language-model agents** through a persistent external artifact.

> Can semantic state persist between independently instantiated agents when the only shared state is an external writable artifact?

This repository intentionally starts small. Phase 0 established one falsifiable relay experiment and its isolation/control invariants. Phase 1 adds self-describing run identity, strict artifact validation, and descriptive paired analysis so real local-model evidence can be collected before the protocol expands.

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
| `NULL` | Literal empty board text |
| `SHUFFLED` | Same board tokens in deterministic random order |
| `RANDOM` | Equal token count of deterministic synthetic noise that excludes writer tokens |

All four reader conditions in a replication are derived from the **same writer output**, making the comparison paired. `SHUFFLED` must actually differ from `REAL`; if the writer emits too little lexical diversity to construct a distinct permutation, the run fails rather than recording a mislabeled control.

Reader-condition execution order is deterministically randomized per replication so model warm-up, throttling, or temporal drift is not perfectly confounded with condition.

## Run locally

Requires Python 3.11+ and an agent command that reads a prompt from stdin and writes its response to stdout.

Run the self-tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
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

Each invocation is a new subprocess. The harness gives it a fresh empty working directory and a small environment allowlist. The model server may remain loaded, but no chat transcript, KV cache, or application conversation state is passed from writer to reader by this harness.

**Runtime restriction:** `CommandAgent` supports pure stdin/stdout model clients only. Do not use tool-capable wrappers or agents with filesystem access. The empty working directory and stripped environment reduce incidental leakage but are not a general-purpose operating-system sandbox.

The output path must be fresh for each CLI invocation. The runner creates a sidecar reservation before any model call and exits if the path already exists or is already reserved, preventing separate runs from being silently mixed. The final JSONL path is not created until every requested replication succeeds; complete records are written to a sibling temporary file and then published atomically. Failed runs therefore do not leave a valid-looking partial result file. Choose a new `--output` path or explicitly remove the old result file before rerunning.

## Phase 1 validation and analysis

Phase 1 keeps the Phase 0 semantic task unchanged. Each CLI-produced record now includes a result schema, one run UUID, the requested replication count, and the base seed. This makes a complete invocation distinguishable from a truncated prefix or a mixture of runs.

Validate a raw run against the frozen Experiment 001 fixture and produce a descriptive summary:

```bash
PYTHONPATH=src python -m semantic_relay.analyze \
  --input results/exp001.jsonl \
  --experiment experiments/001-relay.json \
  --output results/exp001.analysis.json
```

The analyzer independently checks replication completeness, condition membership/order, deterministic seeds, board transformations, hashes, word-budget compliance, and exact-answer scoring. It reports condition accuracies and paired `REAL`-vs-control outcomes. It deliberately performs no significance test.

See [`PHASE1.md`](PHASE1.md) for the validation contract and [`ROADMAP.md`](ROADMAP.md) for the staged progression toward semantic compression and multi-hop persistence.

## Recorded provenance

Each Phase 1 JSONL record includes:

- result schema, run UUID, requested replication count, and base seed;
- experiment and replication identifiers;
- a SHA-256 hash of the complete validated experiment input;
- condition, deterministic transform seed, execution index, and condition-order seed;
- writer and reader command labels;
- pre-write, writer-board, and reader-board SHA-256 hashes;
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
- no tool-capable agents;
- no Kubernetes. Absolutely no fucking Kubernetes. :-)

See [`PROTOCOL.md`](PROTOCOL.md) for the frozen Phase 0 experimental contract, [`PHASE1.md`](PHASE1.md) for apparatus validation, and [`ROADMAP.md`](ROADMAP.md) for later phases.
