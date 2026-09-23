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


## Evidence manifest

After a real run has a fixture-backed analyzer summary, create a retention manifest:

```bash
PYTHONPATH=src python -m semantic_relay.evidence create \
  --input results/<run>.jsonl \
  --analysis results/<run>.analysis.json \
  --experiment experiments/001-relay.json \
  --model-id "<model identifier>" \
  --runtime-version "<runtime version>" \
  --repository-commit "<40-hex-commit>" \
  --output results/<run>.evidence.json
```

The evidence manifest is intentionally **not** ignored by Git. It is small, contains only synthetic/provenance metadata and hashes, and can be committed while the larger raw JSONL and analysis JSON are retained as release/archive assets. The three artifacts must remain available together for the Phase 1 roadmap gate to count as satisfied.
