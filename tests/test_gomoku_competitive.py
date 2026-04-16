import unittest

from gomoku_core import BLACK, WHITE, GameBoard, GomokuAI, forbidden_reason, is_forbidden_move


class CompetitiveRuleTests(unittest.TestCase):
    def test_overline_is_forbidden_for_black(self) -> None:
        board = GameBoard()
        y = 7
        for x in (3, 4, 5, 6, 8):
            self.assertTrue(board.place(x, y, BLACK))

        reason = forbidden_reason(board, 7, y, BLACK)
        self.assertEqual("overline", reason)
        self.assertTrue(is_forbidden_move(board, 7, y, BLACK))

    def test_double_three_is_forbidden_for_black(self) -> None:
        board = GameBoard()
        for x, y in ((6, 7), (8, 7), (7, 6), (7, 8)):
            self.assertTrue(board.place(x, y, BLACK))

        reason = forbidden_reason(board, 7, 7, BLACK)
        self.assertEqual("double_three", reason)

    def test_white_has_no_forbidden_move(self) -> None:
        board = GameBoard()
        for x, y in ((6, 7), (8, 7), (7, 6), (7, 8)):
            self.assertTrue(board.place(x, y, WHITE))

        self.assertIsNone(forbidden_reason(board, 7, 7, WHITE))
        self.assertFalse(is_forbidden_move(board, 7, 7, WHITE))

    def test_ai_respects_legal_checker(self) -> None:
        board = GameBoard()
        y = 7
        for x in (3, 4, 5, 6, 8):
            self.assertTrue(board.place(x, y, BLACK))

        ai = GomokuAI(depth=2, legal_move_checker=lambda b, x, y, s: not is_forbidden_move(b, x, y, s))
        move = ai.best_move(board, BLACK)
        self.assertFalse(is_forbidden_move(board, move.x, move.y, BLACK))


if __name__ == "__main__":
    unittest.main()
