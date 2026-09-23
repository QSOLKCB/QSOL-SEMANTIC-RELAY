import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from semantic_relay.analyze import ValidationError, analyze_file, analyze_records
from semantic_relay.board import sha256_text
from semantic_relay.runner import Experiment, run_replication


class FakeWriter:
    label = "fake-writer"

    def invoke(self, prompt: str) -> str:
        return "K17 has NEMU. NEMU passes Gate 3."


class FakeReader:
    label = "fake-reader"

    def invoke(self, prompt: str) -> str:
        marker = "BOARD:\n"
        question_marker = "\n\nQUESTION:"
        board = prompt.split(marker, 1)[1].split(question_marker, 1)[0]
        if board == "K17 has NEMU. NEMU passes Gate 3.":
            return "K17"
        return "UNKNOWN"


class AnalyzeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.experiment = Experiment(
            experiment_id="test",
            facts=(
                "Object K17 is associated with property NEMU.",
                "Objects with property NEMU are permitted through Gate 3.",
            ),
            question="Which object can pass Gate 3?",
            expected_answer="K17",
            writer_word_budget=30,
        )
        self.run_id = "00000000-0000-4000-8000-000000000001"

    def make_records(self, replicates: int = 3) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for replication_index in range(replicates):
            records.extend(
                run_replication(
                    self.experiment,
                    FakeWriter(),
                    FakeReader(),
                    replication_index,
                    123,
                    run_id=self.run_id,
                    requested_replicates=replicates,
                )
            )
        return records

    def test_valid_run_reports_paired_descriptive_contrasts(self) -> None:
        records = self.make_records()
        summary = analyze_records(
            records,
            source_jsonl_sha256="0" * 64,
            experiment=self.experiment,
        )
        self.assertEqual(summary["validation"], "valid")
        self.assertEqual(summary["observed_replicates"], 3)
        self.assertEqual(summary["accuracy"]["REAL"], 1.0)
        self.assertEqual(summary["accuracy"]["NULL"], 0.0)
        self.assertEqual(summary["accuracy"]["SHUFFLED"], 0.0)
        self.assertEqual(summary["accuracy"]["RANDOM"], 0.0)
        self.assertEqual(summary["contrasts"]["REAL-NULL"]["delta_accuracy"], 1.0)
        self.assertEqual(summary["contrasts"]["REAL-NULL"]["real_only_correct"], 3)

    def test_rejects_incomplete_run(self) -> None:
        records = self.make_records()
        del records[-4:]
        with self.assertRaisesRegex(ValidationError, "expected 12 records"):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_tampered_reader_board(self) -> None:
        records = self.make_records()
        records[0] = dict(records[0])
        records[0]["reader_board"] = "tampered"
        records[0]["reader_board_sha256"] = sha256_text("tampered")
        with self.assertRaisesRegex(ValidationError, "reader_board mismatch"):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_non_string_condition_cleanly(self) -> None:
        records = self.make_records()
        records[0] = dict(records[0])
        records[0]["condition"] = ["REAL"]
        with self.assertRaisesRegex(ValidationError, "condition must be a string"):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_coercively_equal_constant_metadata_types(self) -> None:
        records = self.make_records(1)
        records[1] = dict(records[1])
        records[1]["requested_replicates"] = True
        with self.assertRaisesRegex(
            ValidationError,
            "requested_replicates must have the same type across the run",
        ):
            analyze_records(records, source_jsonl_sha256="0" * 64)

        records = self.make_records(1)
        records[1] = dict(records[1])
        records[1]["base_seed"] = 123.0
        with self.assertRaisesRegex(
            ValidationError,
            "base_seed must have the same type across the run",
        ):
            analyze_records(records, source_jsonl_sha256="0" * 64)

        records = self.make_records(1)
        records[1] = dict(records[1])
        records[1]["writer_word_budget"] = 30.0
        with self.assertRaisesRegex(
            ValidationError,
            "writer_word_budget must have the same type across the run",
        ):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_signed_sha256_syntax(self) -> None:
        records = self.make_records(1)
        signed_digest = "-" + ("0" * 63)
        for record in records:
            record["experiment_input_sha256"] = signed_digest
        with self.assertRaisesRegex(
            ValidationError,
            "experiment_input_sha256 must contain exactly 64 hexadecimal digits",
        ):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_load_jsonl_rejects_duplicate_record_keys(self) -> None:
        records = self.make_records(1)
        lines = [json.dumps(record, sort_keys=True) for record in records]
        lines[0] = lines[0].replace(
            "{",
            '{"reader_output":"AMBIGUOUS",',
            1,
        )
        raw = ("\n".join(lines) + "\n").encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-key.jsonl"
            path.write_bytes(raw)
            with self.assertRaisesRegex(
                ValidationError,
                "line 1 contains duplicate JSON key: reader_output",
            ):
                analyze_file(path)

    def test_load_jsonl_rejects_non_finite_json_constants(self) -> None:
        records = self.make_records(1)
        base_line = json.dumps(records[0], sort_keys=True)

        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                line = base_line.replace(
                    "{",
                    f'{{"extension":{constant},',
                    1,
                )
                raw = (
                    line
                    + "\n"
                    + "\n".join(
                        json.dumps(record, sort_keys=True)
                        for record in records[1:]
                    )
                    + "\n"
                ).encode("utf-8")

                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "non-finite.jsonl"
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(
                        ValidationError,
                        f"line 1 contains non-finite JSON constant: {constant}",
                    ):
                        analyze_file(path)

    def test_rejects_semantically_duplicate_replication_uuids(self) -> None:
        records = self.make_records(2)
        shared = uuid.UUID("12345678-1234-5678-1234-567812345678")
        for record in records:
            record["replication_id"] = (
                str(shared)
                if record["replication_index"] == 0
                else "{" + str(shared) + "}"
            )

        with self.assertRaisesRegex(
            ValidationError,
            "replication_id must be unique across replications",
        ):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_seed_drift(self) -> None:
        records = self.make_records()
        records[0] = dict(records[0])
        records[0]["seed"] += 1
        with self.assertRaisesRegex(ValidationError, "seed mismatch"):
            analyze_records(records, source_jsonl_sha256="0" * 64)

    def test_rejects_fixture_mismatch(self) -> None:
        records = self.make_records()
        changed = Experiment(
            experiment_id=self.experiment.experiment_id,
            facts=self.experiment.facts,
            question="Different question?",
            expected_answer=self.experiment.expected_answer,
            writer_word_budget=self.experiment.writer_word_budget,
        )
        with self.assertRaisesRegex(ValidationError, "does not match fixture"):
            analyze_records(
                records,
                source_jsonl_sha256="0" * 64,
                experiment=changed,
            )

    def test_analyze_file_binds_summary_to_raw_jsonl_hash(self) -> None:
        records = self.make_records(2)
        raw = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
        raw_bytes = raw.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            path.write_bytes(raw_bytes)
            summary = analyze_file(path)
        self.assertEqual(
            summary["source_jsonl_sha256"],
            hashlib.sha256(raw_bytes).hexdigest(),
        )
        self.assertFalse(summary["fixture_verified"])

    def test_analyze_file_hashes_crlf_bytes_without_normalization(self) -> None:
        records = self.make_records(2)
        raw_lf = "".join(
            json.dumps(record, sort_keys=True) + "\n"
            for record in records
        ).encode("utf-8")
        raw_crlf = raw_lf.replace(b"\n", b"\r\n")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run-crlf.jsonl"
            path.write_bytes(raw_crlf)
            summary = analyze_file(path)

        self.assertEqual(
            summary["source_jsonl_sha256"],
            hashlib.sha256(raw_crlf).hexdigest(),
        )
        self.assertNotEqual(
            summary["source_jsonl_sha256"],
            hashlib.sha256(raw_lf).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
