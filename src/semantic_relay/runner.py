from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import tempfile
from typing import Any
import uuid

from .agents import Agent, CommandAgent
from .board import CONDITIONS, sha256_text, transform_board, truncate_words

RESULT_SCHEMA = "qsol.semantic-relay.result.v1"


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    facts: tuple[str, ...]
    question: str
    expected_answer: str
    writer_word_budget: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Experiment":
        experiment_id_raw = raw.get("id")
        if not isinstance(experiment_id_raw, str) or not experiment_id_raw.strip():
            raise ValueError("id must be a non-empty string")

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
        if expected_answer_raw.strip().casefold() == "unknown":
            raise ValueError("expected_answer must not use the reserved UNKNOWN sentinel")

        budget_raw = raw.get("writer_word_budget")
        if isinstance(budget_raw, bool) or not isinstance(budget_raw, int):
            raise ValueError("writer_word_budget must be an integer")
        if budget_raw < 2:
            raise ValueError("writer_word_budget must be at least 2")
        return cls(
            experiment_id=experiment_id_raw.strip(),
            facts=facts,
            question=question_raw.strip(),
            expected_answer=expected_answer_raw.strip(),
            writer_word_budget=budget_raw,
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
    *,
    run_id: str | None = None,
    requested_replicates: int | None = None,
) -> list[dict[str, Any]]:
    if isinstance(replication_index, bool) or not isinstance(replication_index, int):
        raise ValueError("replication_index must be an integer")
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise ValueError("base_seed must be an integer")

    if (run_id is None) != (requested_replicates is None):
        raise ValueError("run_id and requested_replicates must be provided together")
    if run_id is not None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise ValueError("run_id must be a UUID") from exc
        if (
            isinstance(requested_replicates, bool)
            or not isinstance(requested_replicates, int)
            or requested_replicates <= 0
        ):
            raise ValueError("requested_replicates must be a positive integer")
        if not 0 <= replication_index < requested_replicates:
            raise ValueError("replication_index must be within requested_replicates")

    prewrite_board = ""
    writer_raw = writer.invoke(writer_prompt(experiment))
    real_board = truncate_words(writer_raw, experiment.writer_word_budget)
    replication_id = str(uuid.uuid4())
    writer_hash = sha256_text(real_board)
    experiment_hash = experiment.input_sha256
    timestamp = datetime.now(timezone.utc).isoformat()
    condition_order, order_seed = _condition_order(base_seed, replication_index)

    derived_boards: dict[str, tuple[int, str]] = {}
    for condition in CONDITIONS:
        condition_offset = CONDITIONS.index(condition)
        condition_seed = base_seed + (replication_index * 1009) + condition_offset
        derived_boards[condition] = (
            condition_seed,
            transform_board(real_board, condition, condition_seed),
        )

    records: list[dict[str, Any]] = []
    for execution_index, condition in enumerate(condition_order):
        condition_seed, reader_board = derived_boards[condition]
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
        if run_id is not None:
            record = {
                "schema": RESULT_SCHEMA,
                "run_id": run_id,
                "requested_replicates": requested_replicates,
                "base_seed": base_seed,
                **record,
            }
        records.append(record)
    return records


def prepare_output(path: Path) -> Path:
    """Reserve a fresh output name without publishing a result file yet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    reservation = path.parent / f".{path.name}.lock"
    try:
        with reservation.open("x", encoding="utf-8") as handle:
            handle.write("semantic-relay output reservation\n")
    except FileExistsError as exc:
        raise FileExistsError(
            f"output is already reserved: {path}; remove stale reservation {reservation} "
            "only if no run is active"
        ) from exc

    if os.path.lexists(path):
        reservation.unlink(missing_ok=True)
        raise FileExistsError(
            f"output already exists: {path}; choose a new --output or remove it explicitly"
        )
    return reservation


def publish_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write complete records to a sibling temp file, then publish without clobbering."""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, path)
        temp_path.unlink()
        temp_path = None
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


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
        reservation = prepare_output(args.output)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc

    run_id = str(uuid.uuid4())
    all_records: list[dict[str, Any]] = []
    try:
        for replication_index in range(args.replicates):
            records = run_replication(
                experiment,
                writer,
                reader,
                replication_index=replication_index,
                base_seed=args.seed,
                run_id=run_id,
                requested_replicates=args.replicates,
            )
            all_records.extend(records)
            scores = ", ".join(
                f"{record['condition']}={'1' if record['correct'] else '0'}"
                for record in records
            )
            print(f"replication {replication_index}: {scores}")

        publish_jsonl(args.output, all_records)
    finally:
        reservation.unlink(missing_ok=True)

    print(f"wrote results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
