# Phase 0 Experimental Protocol

## Research question

Can task-relevant semantic state be transmitted between independently invoked language-model agents when a persistent external text artifact is the only permitted semantic channel between them?

## Operational definition

A **semantic relay** occurs when a fresh reader agent answers a synthetic-world question more accurately under the `REAL` board condition than under controls, where the answer is not supplied in the reader's prompt except through the board artifact.

The experiment concerns observable information transfer. It makes no claim about consciousness, sentience, subjective experience, autonomous intent, or collective identity.

## Isolation invariant

For every writer-to-reader handoff:

1. The writer receives the synthetic facts and the writer instruction.
2. The writer emits text.
3. The harness truncates that text to the configured word budget and stores it as the writer board.
4. The writer invocation ends.
5. Each reader condition is invoked independently in a new subprocess.
6. Each `CommandAgent` invocation runs in a fresh empty working directory with a small environment allowlist.
7. A reader prompt contains only:
   - its condition-specific board text;
   - the fixed reader instruction; and
   - the experimental question.
8. The harness never includes the writer prompt, writer transcript, or writer process state in a reader prompt.

`CommandAgent` is explicitly restricted to pure stdin/stdout model clients without tool or filesystem access. Its empty working directory and stripped environment reduce incidental leakage but do **not** constitute a universal operating-system sandbox. Tool-capable wrappers are outside the Phase 0 protocol.

The model runtime may cache model weights. Weight reuse is not treated as semantic communication because the experiment does not modify weights.

## Paired control design

One writer board is generated per replication. Four reader boards are derived from that same writer board:

- `REAL`: unchanged writer board;
- `NULL`: literal empty string, rendered without a condition-specific marker;
- `SHUFFLED`: identical whitespace-delimited tokens shuffled using the condition seed and required to differ from `REAL`;
- `RANDOM`: equal number of deterministic synthetic noise tokens generated from the condition seed, with any token present in the writer board rejected and redrawn.

This design controls for writer variation across conditions.

Reader-condition execution order is deterministically permuted once per replication using a separate order seed. Each condition keeps its canonical condition-specific transform seed regardless of execution position. This avoids perfectly confounding condition with model warm-up, service load, throttling, or temporal drift.

## Experiment identity and provenance

The validated experiment input is canonicalized from:

- experiment ID;
- facts;
- question;
- expected answer;
- writer word budget.

A SHA-256 hash of that canonical representation is recorded in every result row. Reusing an experiment ID after changing any material validated input therefore produces a different provenance hash.

## Experiment 001: relay sanity check

The writer sees synthetic, arbitrary facts such as:

```text
Object K17 is associated with property NEMU.
Object R42 is associated with property TAVO.
Objects with property NEMU are permitted through Gate 3.
```

The reader is asked:

```text
Which object can pass Gate 3?
```

The expected answer is `K17`.

The symbols are intentionally artificial to reduce the chance that pretrained knowledge can answer the question.

## Primary metric

For condition `c`:

```text
accuracy(c) = correct(c) / trials(c)
```

Primary contrast:

```text
Delta = accuracy(REAL) - accuracy(NULL)
```

Secondary contrasts compare `REAL` with `SHUFFLED` and `RANDOM`.

Phase 0 does not prescribe a significance test. The first goal is to validate the apparatus and collect enough paired runs to justify a later inferential protocol.

## Success criteria for Phase 0

Phase 0 is considered mechanically successful when:

- automated tests pass;
- every reader invocation is fresh;
- supported agent commands satisfy the no-tools/no-filesystem runtime restriction;
- all four controls run from one writer board per replication;
- condition execution order is deterministically randomized;
- experiment, board, and output hashes are recorded;
- synthetic fixtures are sufficient to score exact answers;
- the results file can be reproduced from a documented command.

A scientific result requires actual model runs and should be reported independently of harness validation.

## Non-goals

Phase 0 will not add:

- autonomous internet access;
- agent-to-agent networking;
- hidden channels;
- long-term memory services;
- embeddings or vector databases;
- orchestration frameworks;
- tool-capable agents;
- model fine-tuning;
- claims beyond the measured relay effect.
