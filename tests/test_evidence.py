import hashlib
import json
import tempfile
import unittest
from unittest.mock import call, patch
from pathlib import Path

from semantic_relay import evidence as evidence_module
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

    def test_rejects_type_coerced_analysis_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            analysis["observed_replicates"] = float(
                analysis["observed_replicates"]
            )
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

    def test_verify_rejects_numeric_type_coercion(self) -> None:
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

            mutations = (
                ("base_seed", float(manifest["base_seed"])),
                (
                    "requested_replicates",
                    float(manifest["requested_replicates"]),
                ),
            )
            for field, replacement in mutations:
                with self.subTest(field=field):
                    mutated = dict(manifest)
                    mutated[field] = replacement
                    manifest_path = root / f"{field}.evidence.json"
                    manifest_path.write_text(
                        json.dumps(mutated, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        ValidationError,
                        "evidence manifest does not match supplied artifacts or metadata",
                    ):
                        verify_evidence_manifest(
                            manifest_path=manifest_path,
                            input_path=input_path,
                            analysis_path=analysis_path,
                            experiment_path=experiment_path,
                        )

            mutated = json.loads(json.dumps(manifest))
            mutated["raw_jsonl"]["size_bytes"] = float(
                mutated["raw_jsonl"]["size_bytes"]
            )
            manifest_path = root / "size.evidence.json"
            manifest_path.write_text(
                json.dumps(mutated, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValidationError,
                "evidence manifest does not match supplied artifacts or metadata",
            ):
                verify_evidence_manifest(
                    manifest_path=manifest_path,
                    input_path=input_path,
                    analysis_path=analysis_path,
                    experiment_path=experiment_path,
                )

    def test_directory_fsync_is_skipped_on_windows(self) -> None:
        directory = Path("evidence")
        with (
            patch("semantic_relay.evidence.os.name", "nt"),
            patch("semantic_relay.evidence.os.open") as open_directory,
            patch("semantic_relay.evidence.os.fsync") as fsync_directory,
        ):
            evidence_module._fsync_directory(directory)

        open_directory.assert_not_called()
        fsync_directory.assert_not_called()

    def test_manifest_publication_syncs_directory_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "run.evidence.json"

            with patch(
                "semantic_relay.evidence._fsync_directory"
            ) as sync_directory:
                write_manifest(path, {"schema": EVIDENCE_SCHEMA})

            self.assertTrue(path.exists())
            self.assertEqual(
                sync_directory.call_args_list,
                [call(root), call(root)],
            )

    def test_manifest_write_failure_publishes_no_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "run.evidence.json"

            def fail_dump(manifest: object, handle: object, **kwargs: object) -> None:
                handle.write('{"partial":')
                raise OSError("simulated write failure")

            with patch("semantic_relay.evidence.json.dump", side_effect=fail_dump):
                with self.assertRaisesRegex(OSError, "simulated write failure"):
                    write_manifest(path, {"schema": EVIDENCE_SCHEMA})

            self.assertFalse(path.exists())
            self.assertEqual(
                list(root.glob(f".{path.name}.*.tmp")),
                [],
            )

    def test_manifest_analyzes_exact_captured_fixture_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, analysis_path, experiment_path = self.make_artifacts(root)
            original_fixture = experiment_path.read_bytes()
            rewritten_fixture = (
                json.dumps(
                    json.loads(original_fixture.decode("utf-8")),
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertNotEqual(original_fixture, rewritten_fixture)

            original_analyze_captured = evidence_module._analyze_captured_artifacts

            def rewrite_then_analyze(
                raw_jsonl: bytes,
                experiment_raw: bytes,
            ) -> dict[str, object]:
                experiment_path.write_bytes(rewritten_fixture)
                return original_analyze_captured(raw_jsonl, experiment_raw)

            with patch(
                "semantic_relay.evidence._analyze_captured_artifacts",
                side_effect=rewrite_then_analyze,
            ):
                manifest = build_evidence_manifest(
                    input_path=input_path,
                    analysis_path=analysis_path,
                    experiment_path=experiment_path,
                    model_id="qwen2.5:3b",
                    runtime_version="ollama 0.99.0",
                    repository_commit="a" * 40,
                )

            self.assertEqual(
                manifest["experiment_fixture"]["sha256"],
                hashlib.sha256(original_fixture).hexdigest(),
            )
            self.assertEqual(
                manifest["experiment_fixture"]["size_bytes"],
                len(original_fixture),
            )
            self.assertEqual(experiment_path.read_bytes(), rewritten_fixture)

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
