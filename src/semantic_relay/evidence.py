from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .analyze import ANALYSIS_SCHEMA, ValidationError, analyze_file

EVIDENCE_SCHEMA = "qsol.semantic-relay.evidence.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _require_nonempty_string(value: Any, field: str) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    _require(bool(value.strip()), f"{field} must be non-empty")
    return value.strip()


def _require_sha256(value: Any, field: str) -> str:
    text = _require_nonempty_string(value, field)
    _require(
        len(text) == 64
        and all(character in "0123456789abcdefABCDEF" for character in text),
        f"{field} must contain exactly 64 hexadecimal digits",
    )
    return text.lower()


def _require_commit_sha(value: Any) -> str:
    text = _require_nonempty_string(value, "repository_commit")
    _require(
        len(text) == 40
        and all(character in "0123456789abcdefABCDEF" for character in text),
        "repository_commit must contain exactly 40 hexadecimal digits",
    )
    return text.lower()


def _reject_non_finite_constant(constant: str) -> None:
    raise ValidationError(f"JSON contains non-finite constant: {constant}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    _require(bool(raw.strip()), f"{label} must not be empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{label} must be valid UTF-8") from exc

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label} is not valid JSON: {exc.msg}") from exc

    _require(isinstance(value, dict), f"{label} must contain a JSON object")
    return raw, value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_descriptor(raw: bytes) -> dict[str, Any]:
    return {
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        # Python's portable os.open/os.fsync path cannot sync directory handles
        # on native Windows. The completed manifest file itself is still fsync'd
        # before the atomic no-clobber hard-link publication.
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_fd = os.open(path, flags)
    except OSError as exc:
        raise ValidationError(
            f"cannot open directory for durability sync: {path}"
        ) from exc
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise ValidationError(
            f"cannot durability-sync directory: {path}"
        ) from exc
    finally:
        os.close(directory_fd)


def _strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return False
        return all(_strict_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _analyze_captured_artifacts(
    raw_jsonl: bytes,
    experiment_raw: bytes,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="semantic-relay-evidence-") as directory:
        snapshot_root = Path(directory)
        input_snapshot = snapshot_root / "run.jsonl"
        experiment_snapshot = snapshot_root / "experiment.json"
        input_snapshot.write_bytes(raw_jsonl)
        experiment_snapshot.write_bytes(experiment_raw)
        return analyze_file(
            input_snapshot,
            experiment_path=experiment_snapshot,
        )


def build_evidence_manifest(
    *,
    input_path: Path,
    analysis_path: Path,
    experiment_path: Path,
    model_id: str,
    runtime_version: str,
    repository_commit: str,
    model_digest: str | None = None,
) -> dict[str, Any]:
    model_id = _require_nonempty_string(model_id, "model_id")
    runtime_version = _require_nonempty_string(runtime_version, "runtime_version")
    repository_commit = _require_commit_sha(repository_commit)
    if model_digest is not None:
        model_digest = _require_nonempty_string(model_digest, "model_digest")

    raw_jsonl = input_path.read_bytes()
    analysis_raw, supplied_analysis = _load_json_object(
        analysis_path,
        "analysis JSON",
    )
    experiment_raw = experiment_path.read_bytes()

    expected_analysis = _analyze_captured_artifacts(
        raw_jsonl,
        experiment_raw,
    )
    _require(
        _strict_equal(supplied_analysis, expected_analysis),
        "analysis JSON does not match fresh fixture-backed analysis of raw JSONL",
    )
    _require(
        supplied_analysis.get("schema") == ANALYSIS_SCHEMA,
        f"analysis JSON schema must be {ANALYSIS_SCHEMA}",
    )
    _require(
        supplied_analysis.get("fixture_verified") is True,
        "analysis JSON must be fixture-verified",
    )

    raw_sha256 = _sha256_bytes(raw_jsonl)
    _require(
        supplied_analysis.get("source_jsonl_sha256") == raw_sha256,
        "analysis JSON source_jsonl_sha256 does not match raw JSONL bytes",
    )

    manifest: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "run_id": supplied_analysis["run_id"],
        "experiment_id": supplied_analysis["experiment_id"],
        "experiment_input_sha256": supplied_analysis["experiment_input_sha256"],
        "model_id": model_id,
        "runtime_version": runtime_version,
        "repository_commit": repository_commit,
        "writer_command": supplied_analysis["writer_agent"],
        "reader_command": supplied_analysis["reader_agent"],
        "base_seed": supplied_analysis["base_seed"],
        "requested_replicates": supplied_analysis["requested_replicates"],
        "raw_jsonl": _file_descriptor(raw_jsonl),
        "analysis_json": {
            **_file_descriptor(analysis_raw),
            "schema": supplied_analysis["schema"],
        },
        "experiment_fixture": _file_descriptor(experiment_raw),
    }
    if model_digest is not None:
        manifest["model_digest"] = model_digest

    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise ValidationError(f"evidence manifest already exists: {path}") from exc

        _fsync_directory(path.parent)
        temp_path.unlink()
        temp_path = None
        _fsync_directory(path.parent)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def load_manifest(path: Path) -> dict[str, Any]:
    _raw, manifest = _load_json_object(path, "evidence manifest")
    _require(
        manifest.get("schema") == EVIDENCE_SCHEMA,
        f"evidence manifest schema must be {EVIDENCE_SCHEMA}",
    )
    return manifest


def verify_evidence_manifest(
    *,
    manifest_path: Path,
    input_path: Path,
    analysis_path: Path,
    experiment_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    rebuilt = build_evidence_manifest(
        input_path=input_path,
        analysis_path=analysis_path,
        experiment_path=experiment_path,
        model_id=_require_nonempty_string(manifest.get("model_id"), "model_id"),
        runtime_version=_require_nonempty_string(
            manifest.get("runtime_version"),
            "runtime_version",
        ),
        repository_commit=_require_commit_sha(manifest.get("repository_commit")),
        model_digest=(
            _require_nonempty_string(manifest.get("model_digest"), "model_digest")
            if "model_digest" in manifest
            else None
        ),
    )
    _require(
        _strict_equal(manifest, rebuilt),
        "evidence manifest does not match supplied artifacts or metadata",
    )
    return rebuilt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify a Phase 1 evidence manifest"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create",
        help="Create a new evidence manifest from validated Phase 1 artifacts",
    )
    create.add_argument("--input", type=Path, required=True)
    create.add_argument("--analysis", type=Path, required=True)
    create.add_argument("--experiment", type=Path, required=True)
    create.add_argument("--model-id", required=True)
    create.add_argument("--model-digest")
    create.add_argument("--runtime-version", required=True)
    create.add_argument("--repository-commit", required=True)
    create.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser(
        "verify",
        help="Verify a retained evidence manifest against its artifacts",
    )
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--analysis", type=Path, required=True)
    verify.add_argument("--experiment", type=Path, required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "create":
            manifest = build_evidence_manifest(
                input_path=args.input,
                analysis_path=args.analysis,
                experiment_path=args.experiment,
                model_id=args.model_id,
                model_digest=args.model_digest,
                runtime_version=args.runtime_version,
                repository_commit=args.repository_commit,
            )
            write_manifest(args.output, manifest)
        else:
            manifest = verify_evidence_manifest(
                manifest_path=args.manifest,
                input_path=args.input,
                analysis_path=args.analysis,
                experiment_path=args.experiment,
            )
    except (OSError, ValidationError, ValueError) as exc:
        raise SystemExit(f"evidence validation failed: {exc}") from exc

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
