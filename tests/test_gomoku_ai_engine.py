import time
import unittest

from gomoku_core import BLACK, WHITE, GameBoard, GomokuAI, Move


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

    def test_rank_moves_keeps_hard_defense_priority_over_killer_history(self) -> None:
        board = GameBoard()
        y = 7
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, y, WHITE))
        self.assertTrue(board.place(7, 9, BLACK))
        self.assertTrue(board.place(8, 9, WHITE))

        ai = GomokuAI(depth=2, time_limit_ms=50, use_threat_space=False)
        normal = (7, 8)
        self.assertEqual(0, board.get(*normal))
        ai._history_table[(BLACK, normal[0], normal[1])] = 10**9
        ai._killer_moves[0] = [normal]

        ranked = ai._rank_moves(board, [Move(4, y), Move(9, y), Move(*normal)], BLACK, ply=0)
        self.assertTrue(ranked)
        self.assertIn((ranked[0].x, ranked[0].y), {(4, y), (9, y)})

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

    def test_vcf_probe_gate_skips_quiet_position(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (7, 7, BLACK),
            (8, 7, WHITE),
            (7, 8, BLACK),
            (8, 8, WHITE),
            (6, 6, BLACK),
            (9, 9, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))
        ai = GomokuAI(depth=3, time_limit_ms=120, use_vcf_probe=True, use_opening_book=False)
        ai._deadline = time.perf_counter() + 1.0
        self.assertFalse(ai._should_trigger_vcf_probe(board, BLACK))

    def test_vcf_probe_gate_triggers_on_enemy_open_four(self) -> None:
        board = GameBoard()
        y = 7
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, y, WHITE))
        self.assertTrue(board.place(7, 8, BLACK))
        self.assertTrue(board.place(10, 10, BLACK))
        ai = GomokuAI(depth=3, time_limit_ms=120, use_vcf_probe=True, use_opening_book=False)
        ai._deadline = time.perf_counter() + 1.0
        self.assertTrue(ai._should_trigger_vcf_probe(board, BLACK))

    def test_four_three_combo_detected_as_must_block(self) -> None:
        board = GameBoard()
        # If White plays (7, 7), it creates a horizontal half-four and a
        # vertical open-three at the same time. Black should treat that point
        # as a mandatory defensive candidate.
        for x, y, stone in (
            (4, 7, BLACK),
            (5, 7, WHITE),
            (6, 7, WHITE),
            (8, 7, WHITE),
            (7, 5, WHITE),
            (7, 6, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))

        ai = GomokuAI(depth=3, time_limit_ms=120, use_opening_book=False)
        board.place(7, 7, WHITE)
        try:
            self.assertTrue(ai._creates_four_three_combo(board, 7, 7, WHITE))
        finally:
            board.remove(7, 7)

        must_block = ai._must_block_moves(board, BLACK)
        self.assertTrue(any((move.x, move.y) == (7, 7) for move in must_block))

    def test_four_three_combo_block_gets_forcing_tier(self) -> None:
        board = GameBoard()
        for x, y, stone in (
            (4, 7, BLACK),
            (5, 7, WHITE),
            (6, 7, WHITE),
            (8, 7, WHITE),
            (7, 5, WHITE),
            (7, 6, WHITE),
        ):
            self.assertTrue(board.place(x, y, stone))

        ai = GomokuAI(depth=3, time_limit_ms=120, use_opening_book=False)
        ranked = ai._rank_moves(board, [Move(7, 7), Move(10, 10)], BLACK, ply=0)

        self.assertEqual((7, 7), (ranked[0].x, ranked[0].y))

    def test_evaluate_board_more_defensive_against_enemy_open_four(self) -> None:
        ai = GomokuAI(depth=2, time_limit_ms=80, use_opening_book=False)
        board_risky = GameBoard()
        for x in (5, 6, 7, 8):
            self.assertTrue(board_risky.place(x, 7, WHITE))
        self.assertTrue(board_risky.place(7, 8, BLACK))

        board_blocked = GameBoard()
        for x in (5, 6, 7, 8):
            self.assertTrue(board_blocked.place(x, 7, WHITE))
        self.assertTrue(board_blocked.place(4, 7, BLACK))
        self.assertTrue(board_blocked.place(7, 8, BLACK))

        risky_score = ai.evaluate_board(board_risky, BLACK)
        blocked_score = ai.evaluate_board(board_blocked, BLACK)
        self.assertGreater(blocked_score, risky_score)

    def test_pattern_lookup_matches_legacy_position_eval(self) -> None:
        board = GameBoard()
        moves = (
            (7, 7, BLACK),
            (8, 7, WHITE),
            (7, 8, BLACK),
            (6, 7, WHITE),
            (7, 6, BLACK),
            (9, 7, WHITE),
            (5, 5, BLACK),
            (5, 6, WHITE),
            (6, 6, BLACK),
            (9, 9, WHITE),
        )
        for x, y, stone in moves:
            self.assertTrue(board.place(x, y, stone))

        lookup_ai = GomokuAI(depth=2, use_line_pattern_lookup=True)
        legacy_ai = GomokuAI(depth=2, use_pattern_lookup=False)
        for phase in ("opening", "middle", "ending"):
            for x, y, stone in moves:
                self.assertEqual(
                    legacy_ai.evaluate_position(board, x, y, stone, phase),
                    lookup_ai.evaluate_position(board, x, y, stone, phase),
                )

    def test_incremental_core_score_matches_full_recompute(self) -> None:
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

        ai = GomokuAI(depth=2, use_opening_book=False, use_incremental_core_eval=True)
        core_black, core_white = ai._core_board_scores(board)
        self.assertEqual((core_black, core_white), ai._core_board_scores(board))

        placed, next_black, next_white, _next_state = ai._place_with_core(board, 7, 9, BLACK, core_black, core_white)
        self.assertTrue(placed)
        self.assertEqual((next_black, next_white), ai._core_board_scores(board))
        self.assertEqual(
            next_black - next_white,
            ai._evaluate_board_from_core(board, BLACK, next_black, next_white),
        )

        board.remove(7, 9)
        self.assertEqual((core_black, core_white), ai._core_board_scores(board))
        self.assertEqual(
            core_white - core_black,
            ai._evaluate_board_from_core(board, WHITE, core_black, core_white),
        )

    def test_segment_core_rewards_double_open_three(self) -> None:
        single = GameBoard()
        for x, y in ((7, 6), (7, 7), (7, 8)):
            self.assertTrue(single.place(x, y, BLACK))

        double = GameBoard()
        for x, y in ((7, 6), (7, 7), (7, 8), (6, 7), (8, 7)):
            self.assertTrue(double.place(x, y, BLACK))

        ai = GomokuAI(depth=2, use_segment_core_eval=True, use_incremental_core_eval=True)
        single_black, _single_white = ai._core_board_scores(single)
        double_black, _double_white = ai._core_board_scores(double)
        self.assertGreater(double_black, single_black + 100_000)

    def test_segment_core_place_matches_full_recompute(self) -> None:
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

        ai = GomokuAI(depth=2, use_segment_core_eval=True, use_incremental_core_eval=True)
        core_black, core_white = ai._core_board_scores(board)
        state = ai._segment_core_state(board)
        placed, next_black, next_white, next_state = ai._place_with_core(
            board, 6, 8, BLACK, core_black, core_white, state
        )
        self.assertTrue(placed)
        self.assertEqual((next_black, next_white), ai._core_board_scores(board))
        self.assertIsNotNone(next_state)
        self.assertEqual((next_state.score_black, next_state.score_white), ai._core_board_scores(board))


if __name__ == "__main__":
    unittest.main()
