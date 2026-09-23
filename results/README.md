# Results

Generated JSONL result files are intentionally ignored by Git.

When publishing a result, record the exact model identifier, runtime version, command, commit SHA, replicate count, seed, and the SHA-256 of the raw JSONL file.


## Phase 1 publication checklist

For a Phase 1 result, retain together:

- the raw JSONL file;
- the analyzer JSON produced with the frozen experiment fixture;
- exact model identifier and model digest/version when available;
- model runtime version;
- exact writer and reader commands;
- repository commit SHA;
- base seed and requested replication count;
- SHA-256 of the raw JSONL file.

Recommended validation command:

```bash
PYTHONPATH=src python -m semantic_relay.analyze \
  --input results/<run>.jsonl \
  --experiment experiments/001-relay.json \
  --output results/<run>.analysis.json
```

The analyzer summary is descriptive evidence about one validated run. It is not a significance test and should not be presented as one.
