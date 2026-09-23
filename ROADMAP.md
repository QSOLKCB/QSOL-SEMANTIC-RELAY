# QSOL-SEMANTIC-RELAY Roadmap

This roadmap is intentionally staged. Later phases are blocked on evidence from earlier phases so the project does not add complexity faster than it adds falsifiability.

## Phase 0 — Minimal relay apparatus — complete

Phase 0 established the smallest useful writer -> persistent text artifact -> fresh reader experiment.

Frozen properties:

- synthetic facts and exact-answer scoring;
- one writer board per replication;
- paired `REAL`, `NULL`, `SHUFFLED`, and `RANDOM` controls;
- fresh restricted subprocess invocation for every agent call;
- deterministic transform seeds and randomized reader-condition order;
- experiment, board, output, and command provenance;
- atomic no-clobber publication of complete JSONL runs.

The Phase 0 experimental semantics remain defined by `PROTOCOL.md`.

## Phase 1 — Apparatus validation and paired analysis — current

Goal: collect real local-model evidence without changing the Phase 0 semantic task.

Implementation contract:

- every CLI run carries a unique run UUID, result-schema identifier, requested replication count, and base seed;
- published JSONL must be complete for the declared replication count;
- an independent analyzer recomputes deterministic condition order, condition seeds, board transforms, hashes, and exact-answer scoring;
- an optional frozen experiment fixture verifies the complete experiment-input hash;
- summaries report descriptive accuracy and paired `REAL`-vs-control outcomes;
- the analyzer does not perform significance testing or make claims beyond the observed run.

Evidence exit criteria:

- at least one documented local-model run is collected with a predeclared replication count;
- the raw JSONL validates against the frozen Experiment 001 fixture;
- model identifier, runtime version, exact command, repository commit, base seed, replication count, raw JSONL SHA-256, and analyzer summary are retained together;
- any failed or invalid run remains distinguishable from a publishable complete run.

## Phase 2 — Semantic compression — blocked on Phase 1 evidence

Only after Phase 1 evidence is validated:

- freeze a family of synthetic relay fixtures;
- predeclare multiple writer word budgets;
- measure how relay accuracy changes as the permitted persistent representation is compressed;
- retain the same isolation and paired-control invariants.

Phase 2 should answer a narrower question than “memory”: how much explicit external text is required to preserve task-relevant structure?

## Phase 3 — Multi-hop persistence — blocked on Phase 2

Only after the compression protocol is stable:

- introduce one or more fresh relay agents between the original writer and final reader;
- ensure each hop sees only the artifact from the immediately previous hop;
- retain paired controls and explicit provenance for every hop;
- measure degradation or preservation across hop depth.

## Still out of scope

Until a later roadmap revision explicitly changes these constraints:

- autonomous networking;
- hidden communication channels;
- vector databases or embedding memory;
- tool-capable agents;
- orchestration frameworks;
- model fine-tuning;
- claims about consciousness, sentience, collective identity, or autonomous intent.
