from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
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
        facts = tuple(str(item).strip() for item in raw["facts"])
        if not facts or any(not item for item in facts):
            raise ValueError("facts must contain at least one non-empty string")
        budget = int(raw["writer_word_budget"])
        if budget <= 0:
            raise ValueError("writer_word_budget must be positive")
        return cls(
            experiment_id=str(raw["id"]),
            facts=facts,
            question=str(raw["question"]).strip(),
            expected_answer=str(raw["expected_answer"]).strip(),
            writer_word_budget=budget,
        )


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
    rendered_board = board if board else "<EMPTY>"
    return (
        "You are the READER in a semantic-relay experiment. You have no access to any "
        "earlier agent context.\n"
        "Use only the board below to answer the question. If the board does not justify "
        "an answer, return UNKNOWN.\n"
        "Return only the answer token with no explanation.\n\n"
        f"BOARD:\n{rendered_board}\n\n"
        f"QUESTION:\n{question}\n"
    )


def normalize_answer(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


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
    timestamp = datetime.now(timezone.utc).isoformat()

    records: list[dict[str, Any]] = []
    for condition_offset, condition in enumerate(CONDITIONS):
        condition_seed = base_seed + (replication_index * 1009) + condition_offset
        reader_board = transform_board(real_board, condition, condition_seed)
        observed = reader.invoke(reader_prompt(reader_board, experiment.question))
        record = {
            "experiment_id": experiment.experiment_id,
            "replication_id": replication_id,
            "replication_index": replication_index,
            "timestamp_utc": timestamp,
            "condition": condition,
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


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
