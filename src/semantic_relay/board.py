from __future__ import annotations

import hashlib
import random

CONDITIONS = ("REAL", "NULL", "SHUFFLED", "RANDOM")
_RANDOM_TOKEN_SPACE = 1_000_000
_RANDOM_COLLISION_ATTEMPTS = 1024


def _is_random_namespace_token(token: str) -> bool:
    return (
        len(token) == 7
        and token.startswith("Z")
        and token[1:].isascii()
        and token[1:].isdigit()
    )


def _find_available_random_token(
    writer_tokens: set[str],
    start: int,
) -> str:
    for offset in range(_RANDOM_TOKEN_SPACE):
        value = (start + offset) % _RANDOM_TOKEN_SPACE
        candidate = f"Z{value:06d}"
        if candidate not in writer_tokens:
            return candidate
    raise ValueError("RANDOM control token namespace is exhausted")


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
    namespace_token_count = sum(
        1 for token in writer_tokens if _is_random_namespace_token(token)
    )
    if namespace_token_count >= _RANDOM_TOKEN_SPACE:
        raise ValueError("RANDOM control token namespace is exhausted")

    random_tokens: list[str] = []
    fallback_candidate: str | None = None
    for _ in tokens:
        if fallback_candidate is not None:
            random_tokens.append(fallback_candidate)
            continue

        for _attempt in range(_RANDOM_COLLISION_ATTEMPTS):
            candidate = f"Z{rng.randrange(_RANDOM_TOKEN_SPACE):06d}"
            if candidate not in writer_tokens:
                random_tokens.append(candidate)
                break
        else:
            fallback_candidate = _find_available_random_token(
                writer_tokens,
                rng.randrange(_RANDOM_TOKEN_SPACE),
            )
            random_tokens.append(fallback_candidate)
    return " ".join(random_tokens)
