from __future__ import annotations

import hashlib
import random

CONDITIONS = ("REAL", "NULL", "SHUFFLED", "RANDOM")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate_words(text: str, limit: int) -> str:
    if limit < 0:
        raise ValueError("word limit must be non-negative")
    return " ".join(text.split()[:limit])


def transform_board(real_board: str, condition: str, seed: int) -> str:
    condition = condition.upper()
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")

    if condition == "REAL":
        return real_board
    if condition == "NULL":
        return ""

    tokens = real_board.split()
    rng = random.Random(seed)

    if condition == "SHUFFLED":
        shuffled = list(tokens)
        rng.shuffle(shuffled)
        return " ".join(shuffled)

    # RANDOM: equal token count, deterministic synthetic noise, and no reuse of
    # writer tokens. The token length is intentionally simple and auditable.
    return " ".join(f"Z{rng.randrange(1_000_000):06d}" for _ in tokens)
