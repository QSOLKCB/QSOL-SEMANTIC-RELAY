import json
import tempfile
import unittest
from pathlib import Path

from semantic_relay.analyze import analyze_file
from semantic_relay.evidence import (
    EVIDENCE_SCHEMA,
    ValidationError,
    build_evidence_manifest,
    verify_evidence_manifest,
    write_manifest,
)
from semantic_relay.runner import Experiment, publish_jsonl, run_replication


class FakeWriter:
    label = "fake-writer"

    def invoke(self, prompt: str) -> str:
        return "K17 has NEMU. NEMU passes Gate 3."


class FakeReader:
    label = "fake-reader"

    def invoke(self, prompt: str) -> str:
        if "K17 has NEMU" in prompt and "NEMU passes Gate 3" in prompt:
            return "K17"
        return "UNKNOWN"


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.experiment = Experiment(
            experiment_id="test-evidence",
            facts=(
                "Object K17 is associated with property NEMU.",
                "Objects with property NEMU are permitted through Gate 3.",
            ),
            question="Which object can pass Gate 3?",
            expected_answer="K17",
            writer_word_budget=30,
        )
        self.run_id = "00000000-0000-4000-8000-000000000001"

    def make_artifacts(self, root: Path) -> tuple[Path, Path, Path]:
        input_path = root / "run.jsonl"
        analysis_path = root / "run.analysis.json"
        experiment_path = root / "experiment.json"

        records = []
        for replication_index in range(2):
            records.extend(
                run_replication(
                    self.experiment,
                    FakeWriter(),
                    FakeReader(),
                    replication_index,
                    1729,
                    run_id=self.run_id,
                    requested_replicates=2,
                )
            )
        publish_jsonl(input_path, records)

        experiment_payload = {
            "id": self.experiment.experiment_id,
            "facts": list(self.experiment.facts),
            "question": self.experiment.question,
            "expected_answer": self.experiment.expected_answer,
            "writer_word_budget": self.experiment.writer_word_budget,
        }
        experiment_path.write_text(
            json.dumps(experiment_payload, indent=2) + "\n",
            encoding="utf-8",
        )

        analysis = analyze_file(
            input_path,
            experiment_path=experiment_path,
        )
        analysis_path.write_text(
            json.dumps(analysis, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return input_path, analysis_path, experiment_path

    def build(self, root: Path) -> dict[str, object]:
        input_path, analysis_path, experiment_path = self.make_artifacts(root)
        return build_evidence_manifest(
            input_path=input_path,
            analysis_path=analysis_path,
            experiment_path=experiment_path,
            model_id="qwen2.5:3b",
            model_digest="sha256:model-digest",
            runtime_version="ollama 0.99.0",
            repository_commit="a" * 40,
        )

    def test_manifest_binds_required_phase1_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.build(root)

        self.assertEqual(manifest["schema"], EVIDENCE_SCHEMA)
        self.assertEqual(manifest["model_id"], "qwen2.5:3b")
        self.assertEqual(manifest["runtime_version"], "ollama 0.99.0")
        self.assertEqual(manifest["repository_commit"], "a" * 40)
        self.assertEqual(manifest["base_seed"], 1729)
        self.assertEqual(manifest["requested_replicates"], 2)
        self.assertEqual(manifest["writer_command"], "fake-writer")
        self.assertEqual(manifest["reader_command"], "fake-reader")
        self.assertEqual(len(manifest["raw_jsonl"]["sha256"]), 64)
        self.assertEqual(len(manifest["analysis_json"]["sha256"]), 64)
        self.assertEqual(len(manifest["experiment_fixture"]["sha256"]), 64)

    def test_rejects_stale_analysis_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            analysis["requested_replicates"] = 999
            analysis_path.write_text(
                json.dumps(analysis, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValidationError,
                "analysis JSON does not match fresh fixture-backed analysis",
            ):
                build_evidence_manifest(
                    input_path=input_path,
                    analysis_path=analysis_path,
                    experiment_path=experiment_path,
                    model_id="qwen2.5:3b",
                    runtime_version="ollama 0.99.0",
                    repository_commit="a" * 40,
                )

    def test_rejects_non_fixture_verified_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            analysis = analyze_file(input_path)
            analysis_path.write_text(
                json.dumps(analysis, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValidationError,
                "analysis JSON does not match fresh fixture-backed analysis",
            ):
                build_evidence_manifest(
                    input_path=input_path,
                    analysis_path=analysis_path,
                    experiment_path=experiment_path,
                    model_id="qwen2.5:3b",
                    runtime_version="ollama 0.99.0",
                    repository_commit="a" * 40,
                )

    def test_verify_detects_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            manifest = build_evidence_manifest(
                input_path=input_path,
                analysis_path=analysis_path,
                experiment_path=experiment_path,
                model_id="qwen2.5:3b",
                runtime_version="ollama 0.99.0",
                repository_commit="a" * 40,
            )
            manifest_path = root / "run.evidence.json"
            write_manifest(manifest_path, manifest)

            input_path.write_bytes(input_path.read_bytes() + b"\n")
            with self.assertRaises(ValidationError):
                verify_evidence_manifest(
                    manifest_path=manifest_path,
                    input_path=input_path,
                    analysis_path=analysis_path,
                    experiment_path=experiment_path,
                )

    def test_verify_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            manifest = build_evidence_manifest(
                input_path=input_path,
                analysis_path=analysis_path,
                experiment_path=experiment_path,
                model_id="qwen2.5:3b",
                model_digest="sha256:model-digest",
                runtime_version="ollama 0.99.0",
                repository_commit="a" * 40,
            )
            manifest_path = root / "run.evidence.json"
            write_manifest(manifest_path, manifest)

            verified = verify_evidence_manifest(
                manifest_path=manifest_path,
                input_path=input_path,
                analysis_path=analysis_path,
                experiment_path=experiment_path,
            )

        self.assertEqual(verified, manifest)

    def test_manifest_write_is_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValidationError,
                "evidence manifest already exists",
            ):
                write_manifest(path, {"schema": EVIDENCE_SCHEMA})


if __name__ == "__main__":
    unittest.main()
