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
6. A reader receives only:
   - its condition-specific board text;
   - the fixed reader instruction; and
   - the experimental question.
7. The harness never includes the writer prompt, writer transcript, or writer process state in a reader prompt.

The model runtime may cache model weights. Weight reuse is not treated as semantic communication because the experiment does not modify weights.

## Paired control design

One writer board is generated per replication. Four reader boards are derived from that same writer board:

- `REAL`: unchanged writer board;
- `NULL`: empty string;
- `SHUFFLED`: identical whitespace-delimited tokens shuffled using the replication seed;
- `RANDOM`: equal number of deterministic synthetic noise tokens generated from the replication seed.

This design controls for writer variation across conditions.

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
- all four controls run from one writer board per replication;
- board/output hashes are recorded;
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
- model fine-tuning;
- claims beyond the measured relay effect.
