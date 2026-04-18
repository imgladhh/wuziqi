import time
import unittest

from gomoku_core import BLACK, WHITE, GameBoard, GomokuAI


class AiEngineUpgradeTests(unittest.TestCase):
    def test_iterative_deepening_respects_time_budget(self) -> None:
        board = GameBoard()
        for x, y, stone in ((7, 7, BLACK), (8, 7, 2), (7, 8, BLACK), (8, 8, 2), (6, 7, BLACK)):
            self.assertTrue(board.place(x, y, stone))

        ai = GomokuAI(depth=5, time_limit_ms=10)
        start = time.perf_counter()
        move = ai.best_move(board, BLACK)
        elapsed = time.perf_counter() - start

        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(0, board.get(move.x, move.y))
        self.assertLess(elapsed, 1.5)

    def test_ai_still_returns_center_on_empty_board(self) -> None:
        board = GameBoard()
        ai = GomokuAI(depth=4, time_limit_ms=20)
        move = ai.best_move(board, BLACK)
        center = board.size // 2
        self.assertEqual((center, center), (move.x, move.y))

    def test_engine_toggles_still_produce_legal_move(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (7, 7, BLACK),
            (8, 7, WHITE),
            (7, 8, BLACK),
            (8, 8, WHITE),
            (6, 7, BLACK),
            (9, 7, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=3, time_limit_ms=30, use_pvs=False, use_quiescence=False, use_threat_space=False)
        move = ai.best_move(board, BLACK)
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(0, board.get(move.x, move.y))

    def test_threat_space_blocks_open_four(self) -> None:
        board = GameBoard()
        y = 7
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, y, WHITE))
        self.assertTrue(board.place(7, 8, BLACK))
        ai = GomokuAI(depth=2, time_limit_ms=50, use_threat_space=True)
        move = ai.best_move(board, BLACK)
        self.assertIn((move.x, move.y), {(4, y), (9, y)})

    def test_must_block_priority_over_heuristic(self) -> None:
        board = GameBoard()
        y = 7
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, y, WHITE))
        self.assertTrue(board.place(7, 8, BLACK))
        ai = GomokuAI(depth=2, time_limit_ms=50, use_threat_space=False)
        moves = ai._candidate_moves(board, BLACK)
        self.assertTrue(moves)
        self.assertIn((moves[0].x, moves[0].y), {(4, y), (9, y)})

    def test_aspiration_and_iid_toggles_run(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (7, 7, BLACK),
            (8, 7, WHITE),
            (7, 8, BLACK),
            (8, 8, WHITE),
            (6, 7, BLACK),
            (9, 7, WHITE),
            (6, 8, BLACK),
            (9, 8, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=4, time_limit_ms=80, use_aspiration=True, use_iid=True, iid_min_depth=3)
        move = ai.best_move(board, BLACK)
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(0, board.get(move.x, move.y))

    def test_eval_correction_is_limited(self) -> None:
        board = GameBoard()
        for x, y, stone in ((7, 7, BLACK), (8, 7, WHITE), (7, 8, BLACK), (8, 8, WHITE)):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=2, use_eval_correction=True, eval_correction_limit=0.1)
        base = 1000
        delta = ai._eval_residual(board, BLACK, base_score=base)
        self.assertLessEqual(abs(delta), int(abs(base) * 0.1))

    def test_lazy_smp_toggle_runs(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (7, 7, BLACK),
            (8, 7, WHITE),
            (7, 8, BLACK),
            (8, 8, WHITE),
            (6, 7, BLACK),
            (9, 7, WHITE),
            (6, 8, BLACK),
            (9, 8, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=3, time_limit_ms=80, use_lazy_smp=True, smp_threads=2, use_opening_book=False)
        move = ai.best_move(board, BLACK)
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(0, board.get(move.x, move.y))

    def test_vct_probe_toggle_runs(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (7, 7, BLACK),
            (8, 7, BLACK),
            (9, 7, BLACK),
            (6, 8, WHITE),
            (8, 8, WHITE),
            (10, 8, WHITE),
            (7, 9, BLACK),
            (9, 9, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=3, time_limit_ms=80, use_vct_probe=True, use_opening_book=False)
        move = ai.best_move(board, BLACK)
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(0, board.get(move.x, move.y))


if __name__ == "__main__":
    unittest.main()
