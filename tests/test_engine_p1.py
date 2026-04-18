import random
import unittest

from engine_p1 import (
    ForbiddenChecker,
    OpeningBook,
    ParallelSearch,
    PatternEvaluator,
    PatternType,
    StateUpdater,
    ThreatLevel,
    ThreatResultType,
    VCTSolver,
    VCFSolver,
)
from gomoku_core import BLACK, WHITE, GameBoard, GomokuAI, Move


class P1ModuleTests(unittest.TestCase):
    def test_state_updater_make_unmake_identity(self) -> None:
        updater = StateUpdater(size=15)
        seed = random.Random(20260417)
        played: list[tuple[Move, int]] = []
        for _ in range(40):
            cands = updater.board.candidate_moves()
            if not cands:
                break
            move = cands[seed.randrange(len(cands))]
            stone = BLACK if len(played) % 2 == 0 else WHITE
            if updater.make_move(move, stone):
                played.append((Move(move.x, move.y), stone))
        snap_before = updater.snapshot_key()
        self.assertTrue(updater.verify_consistency())

        while played:
            move, _stone = played.pop()
            self.assertTrue(updater.unmake_move(move))
            self.assertTrue(updater.verify_consistency())
        snap_after = updater.snapshot_key()
        self.assertNotEqual(snap_before, snap_after)
        self.assertEqual(0, updater.board.move_count)

    def test_pattern_lookup_and_threat_level(self) -> None:
        # .1111. => OPEN_FOUR for BLACK
        cells = [0, BLACK, BLACK, BLACK, BLACK, 0]
        code = PatternEvaluator.encode_window(cells)
        self.assertEqual(PatternType.OPEN_FOUR, PatternEvaluator.classify_window(code, len(cells)))
        level = PatternEvaluator.classify_threat(
            [PatternType.OPEN_FOUR, PatternType.NONE, PatternType.NONE, PatternType.NONE]
        )
        self.assertEqual(ThreatLevel.MUST_BLOCK, level)

    def test_vcf_solver_finds_simple_forcing_win(self) -> None:
        board = GameBoard()
        # Black has open four and should be winning in VCF sense.
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, 7, BLACK))
        self.assertTrue(board.place(7, 8, WHITE))
        self.assertTrue(board.place(8, 8, WHITE))
        solver = VCFSolver()
        result = solver.solve(board, attacker=BLACK, max_depth=4)
        self.assertEqual(ThreatResultType.WIN, result.result)
        self.assertGreaterEqual(result.nodes, 1)

    def test_opening_book_hook_for_ai(self) -> None:
        board = GameBoard()
        book = OpeningBook()
        ai = GomokuAI(depth=2, opening_move_provider=book.query, time_limit_ms=100)
        move = ai.best_move(board, BLACK)
        self.assertEqual((7, 7), (move.x, move.y))

    def test_default_opening_book_provider_in_ai(self) -> None:
        board = GameBoard()
        ai = GomokuAI(depth=2, time_limit_ms=100, use_opening_book=True)
        move = ai.best_move(board, BLACK)
        self.assertEqual((7, 7), (move.x, move.y))

    def test_vcf_probe_root_returns_forcing_move(self) -> None:
        board = GameBoard()
        for x in (5, 6, 7, 8):
            self.assertTrue(board.place(x, 7, BLACK))
        self.assertTrue(board.place(7, 8, WHITE))
        self.assertTrue(board.place(8, 8, WHITE))
        ai = GomokuAI(depth=2, time_limit_ms=100, use_vcf_probe=True, vcf_probe_depth=4, use_opening_book=False)
        move = ai._vcf_probe_root(board, BLACK)
        self.assertIsNotNone(move)
        self.assertIn((move.x, move.y), {(4, 7), (9, 7)})

    def test_vct_solver_handles_open_three_extension(self) -> None:
        board = GameBoard()
        # Build a forcing shape where black can escalate threats.
        for x, y, s in ((7, 7, BLACK), (8, 7, BLACK), (9, 7, BLACK), (6, 8, WHITE), (8, 8, WHITE)):
            self.assertTrue(board.place(x, y, s))
        solver = VCTSolver()
        result = solver.solve(board, attacker=BLACK, max_depth=6)
        self.assertIn(result.result, {ThreatResultType.WIN, ThreatResultType.UNKNOWN})
        self.assertGreaterEqual(result.nodes, 1)

    def test_forbidden_checker_cache_hits(self) -> None:
        board = GameBoard()
        for x, y, s in ((6, 7, BLACK), (8, 7, BLACK), (7, 6, BLACK), (7, 8, BLACK)):
            self.assertTrue(board.place(x, y, s))
        checker = ForbiddenChecker(size=15)
        checker.load_from_board(board)
        first = checker.is_forbidden(7, 7, BLACK)
        second = checker.is_forbidden(7, 7, BLACK)
        self.assertEqual(first, second)
        self.assertGreater(checker.hit_rate, 0.0)

    def test_parallel_search_returns_legal_move(self) -> None:
        board = GameBoard()
        for x, y, s in ((7, 7, BLACK), (8, 7, WHITE), (7, 8, BLACK), (8, 8, WHITE), (6, 7, BLACK), (9, 8, WHITE)):
            self.assertTrue(board.place(x, y, s))
        parallel = ParallelSearch(threads=2, depth_offset=1)

        def builder(_shift: int) -> GomokuAI:
            return GomokuAI(depth=2, time_limit_ms=60, use_lazy_smp=False, use_opening_book=False, use_vcf_probe=False, use_vct_probe=False)

        move = parallel.best_move(board, BLACK, ai_builder=builder)
        self.assertIsNotNone(move)
        self.assertEqual(0, board.get(move.x, move.y))


if __name__ == "__main__":
    unittest.main()
