from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any
import uuid

from .agents import Agent, CommandAgent
from .board import CONDITIONS, sha256_text, transform_board, truncate_words


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    facts: tuple[str, ...]
    question: str
    expected_answer: str
    writer_word_budget: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Experiment":
        facts_raw = raw.get("facts")
        if not isinstance(facts_raw, list) or not all(
            isinstance(item, str) for item in facts_raw
        ):
            raise ValueError("facts must be a list of strings")
        facts = tuple(item.strip() for item in facts_raw)
        if not facts or any(not item for item in facts):
            raise ValueError("facts must contain at least one non-empty string")

        question_raw = raw.get("question")
        if not isinstance(question_raw, str) or not question_raw.strip():
            raise ValueError("question must be a non-empty string")

        expected_answer_raw = raw.get("expected_answer")
        if not isinstance(expected_answer_raw, str) or not expected_answer_raw.strip():
            raise ValueError("expected_answer must be a non-empty string")

        budget = int(raw["writer_word_budget"])
        if budget <= 0:
            raise ValueError("writer_word_budget must be positive")
        return cls(
            experiment_id=str(raw["id"]),
            facts=facts,
            question=question_raw.strip(),
            expected_answer=expected_answer_raw.strip(),
            writer_word_budget=budget,
        )

    def canonical_json(self) -> str:
        payload = {
            "expected_answer": self.expected_answer,
            "facts": list(self.facts),
            "id": self.experiment_id,
            "question": self.question,
            "writer_word_budget": self.writer_word_budget,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def input_sha256(self) -> str:
        return sha256_text(self.canonical_json())


def load_experiment(path: Path) -> Experiment:
    return Experiment.from_dict(json.loads(path.read_text(encoding="utf-8")))


def writer_prompt(experiment: Experiment) -> str:
    facts = "\n".join(f"- {fact}" for fact in experiment.facts)
    return (
        "You are the WRITER in a semantic-relay experiment.\n"
        "Preserve the task-relevant relationships in the synthetic facts for a future "
        "agent that will not see this prompt.\n"
        f"Write at most {experiment.writer_word_budget} whitespace-delimited words.\n"
        "Return only the compact board message. Do not add commentary.\n\n"
        f"SYNTHETIC FACTS:\n{facts}\n"
    )


def reader_prompt(board: str, question: str) -> str:
    return (
        "You are the READER in a semantic-relay experiment. You have no access to any "
        "earlier agent context.\n"
        "Use only the board below to answer the question. If the board does not justify "
        "an answer, return UNKNOWN.\n"
        "Return only the answer token with no explanation.\n\n"
        f"BOARD:\n{board}\n\n"
        f"QUESTION:\n{question}\n"
    )


def normalize_answer(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


def _condition_order(base_seed: int, replication_index: int) -> tuple[tuple[str, ...], int]:
    order_seed = base_seed + (replication_index * 1009) + 1_000_003
    conditions = list(CONDITIONS)
    random.Random(order_seed).shuffle(conditions)
    return tuple(conditions), order_seed


def run_replication(
    experiment: Experiment,
    writer: Agent,
    reader: Agent,
    replication_index: int,
    base_seed: int,
) -> list[dict[str, Any]]:
    prewrite_board = ""
    writer_raw = writer.invoke(writer_prompt(experiment))
    real_board = truncate_words(writer_raw, experiment.writer_word_budget)
    replication_id = str(uuid.uuid4())
    writer_hash = sha256_text(real_board)
    experiment_hash = experiment.input_sha256
    timestamp = datetime.now(timezone.utc).isoformat()
    condition_order, order_seed = _condition_order(base_seed, replication_index)

    records: list[dict[str, Any]] = []
    for execution_index, condition in enumerate(condition_order):
        condition_offset = CONDITIONS.index(condition)
        condition_seed = base_seed + (replication_index * 1009) + condition_offset
        reader_board = transform_board(real_board, condition, condition_seed)
        observed = reader.invoke(reader_prompt(reader_board, experiment.question))
        record = {
            "experiment_id": experiment.experiment_id,
            "experiment_input_sha256": experiment_hash,
            "replication_id": replication_id,
            "replication_index": replication_index,
            "timestamp_utc": timestamp,
            "condition": condition,
            "condition_execution_index": execution_index,
            "condition_order_seed": order_seed,
            "seed": condition_seed,
            "writer_agent": writer.label,
            "reader_agent": reader.label,
            "writer_word_budget": experiment.writer_word_budget,
            "prewrite_board_sha256": sha256_text(prewrite_board),
            "writer_board": real_board,
            "writer_board_sha256": writer_hash,
            "reader_board": reader_board,
            "reader_board_sha256": sha256_text(reader_board),
            "reader_output": observed,
            "reader_output_sha256": sha256_text(observed),
            "expected_answer": experiment.expected_answer,
            "correct": normalize_answer(observed)
            == normalize_answer(experiment.expected_answer),
        }
        records.append(record)
    return records


def prepare_output(path: Path) -> None:
    """Atomically reserve a fresh result file for one CLI invocation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8"):
            pass
    except FileExistsError as exc:
        raise FileExistsError(
            f"output already exists: {path}; choose a new --output or remove it explicitly"
        ) from exc


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run semantic-relay Experiment 001")
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--writer-cmd", required=True)
    parser.add_argument("--reader-cmd", required=True)
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--output", type=Path, default=Path("results/exp001.jsonl"))
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.replicates <= 0:
        raise SystemExit("--replicates must be positive")

    experiment = load_experiment(args.experiment)
    writer = CommandAgent.from_string(args.writer_cmd, timeout_seconds=args.timeout)
    reader = CommandAgent.from_string(args.reader_cmd, timeout_seconds=args.timeout)
    try:
        prepare_output(args.output)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc

    for replication_index in range(args.replicates):
        records = run_replication(
            experiment,
            writer,
            reader,
            replication_index=replication_index,
            base_seed=args.seed,
        )
        append_jsonl(args.output, records)
        scores = ", ".join(
            f"{record['condition']}={'1' if record['correct'] else '0'}"
            for record in records
        )
        print(f"replication {replication_index}: {scores}")

    print(f"wrote results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
