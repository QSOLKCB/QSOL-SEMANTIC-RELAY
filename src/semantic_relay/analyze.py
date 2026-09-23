from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import uuid
from typing import Any

from .board import CONDITIONS, sha256_text, transform_board
from .runner import Experiment, RESULT_SCHEMA, load_experiment, normalize_answer

ANALYSIS_SCHEMA = "qsol.semantic-relay.analysis.v1"

_REQUIRED_FIELDS = {
    "schema",
    "run_id",
    "requested_replicates",
    "base_seed",
    "experiment_id",
    "experiment_input_sha256",
    "replication_id",
    "replication_index",
    "timestamp_utc",
    "condition",
    "condition_execution_index",
    "condition_order_seed",
    "seed",
    "writer_agent",
    "reader_agent",
    "writer_word_budget",
    "prewrite_board_sha256",
    "writer_board",
    "writer_board_sha256",
    "reader_board",
    "reader_board_sha256",
    "reader_output",
    "reader_output_sha256",
    "expected_answer",
    "correct",
}


class ValidationError(ValueError):
    """Raised when a result artifact violates the Phase 1 run contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _require_int(value: Any, field: str, *, minimum: int | None = None) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{field} must be an integer",
    )
    if minimum is not None:
        _require(value >= minimum, f"{field} must be >= {minimum}")
    return value


def _require_string(value: Any, field: str, *, nonempty: bool = True) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    if nonempty:
        _require(bool(value.strip()), f"{field} must be non-empty")
    return value


def _require_sha256(value: Any, field: str) -> str:
    text = _require_string(value, field)
    _require(
        len(text) == 64
        and all(character in "0123456789abcdefABCDEF" for character in text),
        f"{field} must contain exactly 64 hexadecimal digits",
    )
    return text.lower()


def _single(records: list[dict[str, Any]], field: str) -> Any:
    first = records[0][field]
    first_type = type(first)
    for record in records[1:]:
        value = record[field]
        _require(
            type(value) is first_type,
            f"{field} must have the same type across the run",
        )
        _require(value == first, f"{field} must be constant across the run")
    return first


def _expected_condition_order(base_seed: int, replication_index: int) -> tuple[tuple[str, ...], int]:
    order_seed = base_seed + (replication_index * 1009) + 1_000_003
    conditions = list(CONDITIONS)
    random.Random(order_seed).shuffle(conditions)
    return tuple(conditions), order_seed


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
    line_number: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(
            key not in result,
            f"line {line_number} contains duplicate JSON key: {key}",
        )
        result[key] = value
    return result


def _reject_non_finite_json_constant(
    constant: str,
    line_number: int,
) -> None:
    raise ValidationError(
        f"line {line_number} contains non-finite JSON constant: {constant}"
    )


def load_jsonl(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    _require(bool(raw.strip()), "result JSONL must not be empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("result JSONL must be valid UTF-8") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        _require(bool(line.strip()), f"line {line_number} must not be blank")
        try:
            record = json.loads(
                line,
                object_pairs_hook=lambda pairs: _object_without_duplicate_keys(
                    pairs,
                    line_number,
                ),
                parse_constant=lambda constant: _reject_non_finite_json_constant(
                    constant,
                    line_number,
                ),
            )
        except json.JSONDecodeError as exc:
            raise ValidationError(f"line {line_number} is not valid JSON: {exc.msg}") from exc
        _require(isinstance(record, dict), f"line {line_number} must contain a JSON object")
        records.append(record)

    return raw, records


def _validate_records(
    records: list[dict[str, Any]],
    experiment: Experiment | None,
) -> tuple[dict[str, Any], dict[int, list[dict[str, Any]]]]:
    _require(bool(records), "result set must contain at least one record")

    for line_number, record in enumerate(records, start=1):
        missing = sorted(_REQUIRED_FIELDS.difference(record))
        _require(not missing, f"record {line_number} is missing fields: {', '.join(missing)}")

    schema = _single(records, "schema")
    _require(schema == RESULT_SCHEMA, f"unsupported result schema: {schema!r}")

    run_id = _require_string(_single(records, "run_id"), "run_id")
    try:
        uuid.UUID(run_id)
    except ValueError as exc:
        raise ValidationError("run_id must be a UUID") from exc

    requested_replicates = _require_int(
        _single(records, "requested_replicates"),
        "requested_replicates",
        minimum=1,
    )
    base_seed = _require_int(_single(records, "base_seed"), "base_seed")

    experiment_id = _require_string(_single(records, "experiment_id"), "experiment_id")
    experiment_hash = _require_sha256(
        _single(records, "experiment_input_sha256"),
        "experiment_input_sha256",
    )
    writer_agent = _require_string(_single(records, "writer_agent"), "writer_agent")
    reader_agent = _require_string(_single(records, "reader_agent"), "reader_agent")
    writer_word_budget = _require_int(
        _single(records, "writer_word_budget"),
        "writer_word_budget",
        minimum=2,
    )
    expected_answer = _require_string(_single(records, "expected_answer"), "expected_answer")
    _require(
        expected_answer.strip().casefold() != "unknown",
        "expected_answer must not use the reserved UNKNOWN sentinel",
    )

    expected_record_count = requested_replicates * len(CONDITIONS)
    _require(
        len(records) == expected_record_count,
        f"expected {expected_record_count} records for {requested_replicates} replications, "
        f"found {len(records)}",
    )

    if experiment is not None:
        _require(experiment.experiment_id == experiment_id, "experiment_id does not match fixture")
        _require(
            experiment.input_sha256 == experiment_hash,
            "experiment_input_sha256 does not match fixture",
        )
        _require(
            experiment.expected_answer == expected_answer,
            "expected_answer does not match fixture",
        )
        _require(
            experiment.writer_word_budget == writer_word_budget,
            "writer_word_budget does not match fixture",
        )

    groups: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        replication_index = _require_int(
            record["replication_index"],
            "replication_index",
            minimum=0,
        )
        _require(
            replication_index < requested_replicates,
            "replication_index exceeds requested_replicates",
        )
        groups.setdefault(replication_index, []).append(record)

    _require(
        set(groups) == set(range(requested_replicates)),
        "replication indices must be exactly 0..requested_replicates-1",
    )

    seen_replication_ids: set[uuid.UUID] = set()
    empty_hash = sha256_text("")

    for replication_index in range(requested_replicates):
        group = groups[replication_index]
        _require(
            len(group) == len(CONDITIONS),
            f"replication {replication_index} must contain exactly {len(CONDITIONS)} records",
        )

        replication_id = _require_string(group[0]["replication_id"], "replication_id")
        _require(
            all(record["replication_id"] == replication_id for record in group),
            f"replication {replication_index} has multiple replication_id values",
        )
        try:
            parsed_replication_id = uuid.UUID(replication_id)
        except ValueError as exc:
            raise ValidationError("replication_id must be a UUID") from exc
        _require(
            parsed_replication_id not in seen_replication_ids,
            "replication_id must be unique across replications",
        )
        seen_replication_ids.add(parsed_replication_id)

        timestamp = _require_string(group[0]["timestamp_utc"], "timestamp_utc")
        _require(
            all(record["timestamp_utc"] == timestamp for record in group),
            f"replication {replication_index} has multiple timestamps",
        )
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValidationError("timestamp_utc must be ISO-8601") from exc
        _require(
            parsed_timestamp.tzinfo is not None and parsed_timestamp.utcoffset() is not None,
            "timestamp_utc must include a timezone",
        )

        writer_board = _require_string(group[0]["writer_board"], "writer_board", nonempty=False)
        writer_hash = _require_sha256(group[0]["writer_board_sha256"], "writer_board_sha256")
        _require(writer_hash == sha256_text(writer_board), "writer_board_sha256 mismatch")
        _require(
            all(record["writer_board"] == writer_board for record in group),
            f"replication {replication_index} has multiple writer boards",
        )
        _require(
            all(
                _require_sha256(
                    record["writer_board_sha256"],
                    "writer_board_sha256",
                )
                == writer_hash
                for record in group
            ),
            f"replication {replication_index} has multiple writer board hashes",
        )
        _require(
            len(writer_board.split()) <= writer_word_budget,
            f"replication {replication_index} exceeds writer_word_budget",
        )

        validated_conditions: list[str] = []
        for record in group:
            condition = _require_string(record["condition"], "condition")
            _require(condition in CONDITIONS, f"unknown condition: {condition}")
            validated_conditions.append(condition)
        _require(
            set(validated_conditions) == set(CONDITIONS),
            f"replication {replication_index} must contain each condition exactly once",
        )

        execution_indices = [
            _require_int(
                record["condition_execution_index"],
                "condition_execution_index",
                minimum=0,
            )
            for record in group
        ]
        _require(
            sorted(execution_indices) == list(range(len(CONDITIONS))),
            f"replication {replication_index} has invalid condition execution indices",
        )

        expected_order, expected_order_seed = _expected_condition_order(
            base_seed,
            replication_index,
        )
        ordered = sorted(group, key=lambda record: record["condition_execution_index"])
        _require(
            tuple(record["condition"] for record in ordered) == expected_order,
            f"replication {replication_index} condition order does not match base_seed",
        )

        for record in group:
            condition = record["condition"]
            _require(isinstance(condition, str), "condition must be a string")
            condition_offset = CONDITIONS.index(condition)
            expected_seed = base_seed + (replication_index * 1009) + condition_offset

            _require_int(record["seed"], "seed")
            _require(
                record["seed"] == expected_seed,
                f"replication {replication_index} {condition} seed mismatch",
            )
            _require_int(record["condition_order_seed"], "condition_order_seed")
            _require(
                record["condition_order_seed"] == expected_order_seed,
                f"replication {replication_index} condition_order_seed mismatch",
            )

            _require(
                _require_sha256(
                    record["prewrite_board_sha256"],
                    "prewrite_board_sha256",
                )
                == empty_hash,
                "prewrite_board_sha256 must be the empty-board hash",
            )

            reader_board = _require_string(
                record["reader_board"],
                "reader_board",
                nonempty=False,
            )
            try:
                expected_reader_board = transform_board(
                    writer_board,
                    condition,
                    expected_seed,
                )
            except ValueError as exc:
                raise ValidationError(
                    f"replication {replication_index} {condition} transform invalid: {exc}"
                ) from exc
            _require(
                reader_board == expected_reader_board,
                f"replication {replication_index} {condition} reader_board mismatch",
            )
            _require(
                _require_sha256(
                    record["reader_board_sha256"],
                    "reader_board_sha256",
                )
                == sha256_text(reader_board),
                f"replication {replication_index} {condition} reader_board_sha256 mismatch",
            )

            reader_output = _require_string(
                record["reader_output"],
                "reader_output",
                nonempty=False,
            )
            _require(
                _require_sha256(
                    record["reader_output_sha256"],
                    "reader_output_sha256",
                )
                == sha256_text(reader_output),
                f"replication {replication_index} {condition} reader_output_sha256 mismatch",
            )

            _require(isinstance(record["correct"], bool), "correct must be boolean")
            expected_correct = normalize_answer(reader_output) == normalize_answer(
                expected_answer
            )
            _require(
                record["correct"] is expected_correct,
                f"replication {replication_index} {condition} correctness mismatch",
            )

    metadata = {
        "schema": schema,
        "run_id": run_id,
        "requested_replicates": requested_replicates,
        "base_seed": base_seed,
        "experiment_id": experiment_id,
        "experiment_input_sha256": experiment_hash,
        "writer_agent": writer_agent,
        "reader_agent": reader_agent,
        "writer_word_budget": writer_word_budget,
        "expected_answer": expected_answer,
    }
    return metadata, groups


def analyze_records(
    records: list[dict[str, Any]],
    *,
    source_jsonl_sha256: str,
    experiment: Experiment | None = None,
) -> dict[str, Any]:
    metadata, groups = _validate_records(records, experiment)
    replication_count = metadata["requested_replicates"]

    accuracy: dict[str, float] = {}
    correct_counts: dict[str, int] = {}
    for condition in CONDITIONS:
        count = sum(
            1
            for group in groups.values()
            for record in group
            if record["condition"] == condition and record["correct"]
        )
        correct_counts[condition] = count
        accuracy[condition] = count / replication_count

    contrasts: dict[str, dict[str, Any]] = {}
    for control in ("NULL", "SHUFFLED", "RANDOM"):
        real_only = 0
        control_only = 0
        both_correct = 0
        both_wrong = 0
        for replication_index in range(replication_count):
            by_condition = {
                record["condition"]: record
                for record in groups[replication_index]
            }
            real_correct = by_condition["REAL"]["correct"]
            control_correct = by_condition[control]["correct"]
            if real_correct and not control_correct:
                real_only += 1
            elif control_correct and not real_correct:
                control_only += 1
            elif real_correct and control_correct:
                both_correct += 1
            else:
                both_wrong += 1

        contrasts[f"REAL-{control}"] = {
            "delta_accuracy": accuracy["REAL"] - accuracy[control],
            "real_only_correct": real_only,
            "control_only_correct": control_only,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
        }

    return {
        "schema": ANALYSIS_SCHEMA,
        "source_schema": metadata["schema"],
        "source_jsonl_sha256": _require_sha256(
            source_jsonl_sha256,
            "source_jsonl_sha256",
        ),
        "run_id": metadata["run_id"],
        "experiment_id": metadata["experiment_id"],
        "experiment_input_sha256": metadata["experiment_input_sha256"],
        "requested_replicates": replication_count,
        "observed_replicates": len(groups),
        "record_count": len(records),
        "base_seed": metadata["base_seed"],
        "writer_agent": metadata["writer_agent"],
        "reader_agent": metadata["reader_agent"],
        "writer_word_budget": metadata["writer_word_budget"],
        "fixture_verified": experiment is not None,
        "validation": "valid",
        "correct_counts": correct_counts,
        "accuracy": accuracy,
        "contrasts": contrasts,
    }


def analyze_file(
    input_path: Path,
    *,
    experiment_path: Path | None = None,
) -> dict[str, Any]:
    raw, records = load_jsonl(input_path)
    experiment = load_experiment(experiment_path) if experiment_path is not None else None
    return analyze_records(
        records,
        source_jsonl_sha256=hashlib.sha256(raw).hexdigest(),
        experiment=experiment,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and summarize a Phase 1 semantic-relay JSONL run"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = analyze_file(
            args.input,
            experiment_path=args.experiment,
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise SystemExit(f"validation failed: {exc}") from exc

    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        except FileExistsError as exc:
            raise SystemExit(f"analysis output already exists: {args.output}") from exc

    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
