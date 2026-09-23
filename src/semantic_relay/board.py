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
        if len(tokens) < 2 or len(set(tokens)) < 2:
            raise ValueError(
                "SHUFFLED control requires at least two distinct board tokens"
            )
        shuffled = list(tokens)
        rng.shuffle(shuffled)
        if shuffled == tokens:
            swap_index = next(
                index for index, token in enumerate(tokens[1:], start=1)
                if token != tokens[0]
            )
            shuffled[0], shuffled[swap_index] = shuffled[swap_index], shuffled[0]
        return " ".join(shuffled)

    writer_tokens = set(tokens)
    random_tokens: list[str] = []
    for _ in tokens:
        while True:
            candidate = f"Z{rng.randrange(1_000_000):06d}"
            if candidate not in writer_tokens:
                random_tokens.append(candidate)
                break
    return " ".join(random_tokens)
