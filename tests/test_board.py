import unittest

from semantic_relay.board import sha256_text, transform_board, truncate_words


class BoardTests(unittest.TestCase):
    def test_truncate_words_enforces_budget(self) -> None:
        self.assertEqual(truncate_words("one two three four", 3), "one two three")

    def test_shuffled_preserves_multiset_and_differs_from_real(self) -> None:
        board = "K17 NEMU Gate3 pass"
        shuffled = transform_board(board, "SHUFFLED", seed=7)
        self.assertEqual(sorted(shuffled.split()), sorted(board.split()))
        self.assertNotEqual(shuffled, board)

    def test_shuffled_fallback_changes_identity_permutation(self) -> None:
        board = "alpha beta gamma"
        for seed in range(20):
            shuffled = transform_board(board, "SHUFFLED", seed=seed)
            self.assertNotEqual(shuffled, board)

    def test_shuffled_rejects_board_without_distinct_permutation(self) -> None:
        for board in ("ONLY", "same same"):
            with self.subTest(board=board):
                with self.assertRaisesRegex(
                    ValueError,
                    "SHUFFLED control requires at least two distinct board tokens",
                ):
                    transform_board(board, "SHUFFLED", seed=1)

    def test_random_preserves_token_count_not_tokens(self) -> None:
        board = "K17 NEMU Gate3 pass"
        random_board = transform_board(board, "RANDOM", seed=7)
        self.assertEqual(len(random_board.split()), len(board.split()))
        self.assertTrue(set(random_board.split()).isdisjoint(board.split()))

    def test_null_is_empty(self) -> None:
        self.assertEqual(transform_board("anything", "NULL", seed=1), "")

    def test_hash_is_stable(self) -> None:
        self.assertEqual(
            sha256_text("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


if __name__ == "__main__":
    unittest.main()
