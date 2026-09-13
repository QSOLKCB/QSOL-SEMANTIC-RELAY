import tempfile
import unittest
from pathlib import Path

from semantic_relay.runner import (
    Experiment,
    append_jsonl,
    prepare_output,
    run_replication,
)


class FakeWriter:
    label = "fake-writer"

    def invoke(self, prompt: str) -> str:
        self.last_prompt = prompt
        return "K17 has NEMU. NEMU passes Gate 3."


class FakeReader:
    label = "fake-reader"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "K17 has NEMU" in prompt and "NEMU passes Gate 3" in prompt:
            return "K17"
        return "UNKNOWN"


class RunnerTests(unittest.TestCase):
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

    def valid_raw_experiment(self) -> dict[str, object]:
        return {
            "id": "test",
            "facts": [
                "Object K17 is associated with property NEMU.",
                "Objects with property NEMU are permitted through Gate 3.",
            ],
            "question": "Which object can pass Gate 3?",
            "expected_answer": "K17",
            "writer_word_budget": 30,
        }

    def test_replication_uses_one_writer_and_four_fresh_reader_invocations(self) -> None:
        writer = FakeWriter()
        reader = FakeReader()
        records = run_replication(self.experiment, writer, reader, 0, 123)
        self.assertEqual(len(records), 4)
        self.assertEqual(len(reader.prompts), 4)
        self.assertEqual(
            [r["condition"] for r in records],
            ["REAL", "NULL", "SHUFFLED", "RANDOM"],
        )
        self.assertTrue(records[0]["correct"])
        self.assertFalse(records[1]["correct"])

    def test_all_conditions_share_writer_board_hash(self) -> None:
        records = run_replication(self.experiment, FakeWriter(), FakeReader(), 1, 123)
        hashes = {record["writer_board_sha256"] for record in records}
        self.assertEqual(len(hashes), 1)

    def test_jsonl_append_to_reserved_file(self) -> None:
        records = run_replication(self.experiment, FakeWriter(), FakeReader(), 2, 123)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.jsonl"
            prepare_output(path)
            append_jsonl(path, records)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 4)

    def test_prepare_output_rejects_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.jsonl"
            prepare_output(path)
            with self.assertRaises(FileExistsError):
                prepare_output(path)

    def test_experiment_rejects_scalar_facts(self) -> None:
        raw = self.valid_raw_experiment()
        raw["facts"] = "K17 has NEMU"
        with self.assertRaisesRegex(ValueError, "facts must be a list of strings"):
            Experiment.from_dict(raw)

    def test_experiment_rejects_non_string_fact(self) -> None:
        raw = self.valid_raw_experiment()
        raw["facts"] = ["valid", 17]
        with self.assertRaisesRegex(ValueError, "facts must be a list of strings"):
            Experiment.from_dict(raw)

    def test_experiment_rejects_empty_expected_answer(self) -> None:
        raw = self.valid_raw_experiment()
        raw["expected_answer"] = "   "
        with self.assertRaisesRegex(ValueError, "expected_answer must be a non-empty string"):
            Experiment.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
