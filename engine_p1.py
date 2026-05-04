from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from gomoku_core import BLACK, EMPTY, WHITE, DIRECTIONS, GameBoard, Move, opponent


class PatternType(str, Enum):
    FIVE = "FIVE"
    OPEN_FOUR = "OPEN_FOUR"
    FOUR = "FOUR"
    OPEN_THREE = "OPEN_THREE"
    THREE = "THREE"
    TWO = "TWO"
    NONE = "NONE"


class ThreatLevel(str, Enum):
    WIN = "WIN"
    MUST_BLOCK = "MUST_BLOCK"
    FORCING = "FORCING"
    NORMAL = "NORMAL"


class ThreatResultType(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    UNKNOWN = "UNKNOWN"


@dataclass
class ThreatResult:
    result: ThreatResultType
    pv: List[Tuple[int, int]]
    nodes: int


class PatternEvaluator:
    @staticmethod
    def classify_window(window_code: int, length: int = 7) -> PatternType:
        cells = PatternEvaluator.decode_window(window_code, length)
        return PatternEvaluator.classify_cells(cells, BLACK)

    @staticmethod
    def encode_window(cells: Sequence[int]) -> int:
        code = 0
        for value in cells:
            code = code * 3 + value
        return code

    @staticmethod
    def decode_window(code: int, length: int) -> List[int]:
        cells = [0] * length
        for i in range(length - 1, -1, -1):
            cells[i] = code % 3
            code //= 3
        return cells

    @staticmethod
    def classify_cells(cells: Sequence[int], stone: int) -> PatternType:
        if not cells:
            return PatternType.NONE
        enemy = opponent(stone)
        view = [1 if c == stone else 2 if c == enemy else 0 for c in cells]

        longest = 0
        open_ends_for_longest = 0
        i = 0
        while i < len(view):
            if view[i] != 1:
                i += 1
                continue
            j = i
            while j < len(view) and view[j] == 1:
                j += 1
            run = j - i
            left_open = i - 1 >= 0 and view[i - 1] == 0
            right_open = j < len(view) and view[j] == 0
            opens = (1 if left_open else 0) + (1 if right_open else 0)
            if run > longest or (run == longest and opens > open_ends_for_longest):
                longest = run
                open_ends_for_longest = opens
            i = j

        if longest >= 5:
            return PatternType.FIVE
        if longest == 4 and open_ends_for_longest == 2:
            return PatternType.OPEN_FOUR
        if longest == 4 and open_ends_for_longest == 1:
            return PatternType.FOUR
        if longest == 3 and open_ends_for_longest == 2:
            return PatternType.OPEN_THREE
        if longest == 3:
            return PatternType.THREE
        if longest == 2:
            return PatternType.TWO
        return PatternType.NONE

    @staticmethod
    def classify_directions(board: GameBoard, x: int, y: int, stone: int) -> List[PatternType]:
        result: List[PatternType] = []
        for dx, dy in DIRECTIONS:
            cells: List[int] = []
            for offset in range(-3, 4):
                px, py = x + offset * dx, y + offset * dy
                if not board.is_inside(px, py):
                    cells.append(opponent(stone))
                else:
                    cells.append(board.get(px, py))
            result.append(PatternEvaluator.classify_cells(cells, stone))
        return result

    @staticmethod
    def classify_threat(patterns: Sequence[PatternType]) -> ThreatLevel:
        if any(p == PatternType.FIVE for p in patterns):
            return ThreatLevel.WIN
        open_four_count = sum(1 for p in patterns if p == PatternType.OPEN_FOUR)
        four_count = sum(1 for p in patterns if p in (PatternType.OPEN_FOUR, PatternType.FOUR))
        open_three_count = sum(1 for p in patterns if p == PatternType.OPEN_THREE)
        if open_four_count >= 1 or four_count >= 2:
            return ThreatLevel.MUST_BLOCK
        if open_three_count >= 1 or four_count >= 1:
            return ThreatLevel.FORCING
        return ThreatLevel.NORMAL


class StateUpdater:
    def __init__(self, size: int = 15) -> None:
        self.board = GameBoard(size=size)
        self._rng = random.Random(0xC0FFEE)
        self._zobrist = [
            [(self._rng.getrandbits(64), self._rng.getrandbits(64)) for _ in range(size)]
            for _ in range(size)
        ]
        self.zobrist = 0
        self.line_codes: Dict[Tuple[str, int], int] = {}
        self.pattern_cache: Dict[Tuple[str, int], PatternType] = {}
        self.legality_cache: Dict[Tuple[int, int, int], bool] = {}
        self._rebuild_all()

    def make_move(self, move: Move, stone: int) -> bool:
        if not self.board.place(move.x, move.y, stone):
            return False
        self.zobrist ^= self._zobrist[move.x][move.y][0 if stone == BLACK else 1]
        self._update_affected_lines(move.x, move.y, stone)
        self.legality_cache.clear()
        return True

    def unmake_move(self, move: Move) -> bool:
        if not self.board.is_inside(move.x, move.y):
            return False
        stone = self.board.get(move.x, move.y)
        if stone == EMPTY:
            return False
        self.board.remove(move.x, move.y)
        self.zobrist ^= self._zobrist[move.x][move.y][0 if stone == BLACK else 1]
        self._update_affected_lines(move.x, move.y, stone)
        self.legality_cache.clear()
        return True

    def verify_consistency(self) -> bool:
        original_hash = self.zobrist
        original_lines = dict(self.line_codes)
        original_patterns = dict(self.pattern_cache)
        self._rebuild_all()
        ok = (self.zobrist == original_hash) and (self.line_codes == original_lines) and (
            self.pattern_cache == original_patterns
        )
        return ok

    def snapshot_key(self) -> Tuple[int, Tuple[Tuple[int, ...], ...]]:
        return self.zobrist, self.board.state_key()

    def _rebuild_all(self) -> None:
        self.zobrist = 0
        self.line_codes.clear()
        self.pattern_cache.clear()
        size = self.board.size
        for x in range(size):
            for y in range(size):
                stone = self.board.get(x, y)
                if stone != EMPTY:
                    self.zobrist ^= self._zobrist[x][y][0 if stone == BLACK else 1]
        for idx in range(size):
            self._recompute_row(idx)
            self._recompute_col(idx)
        for diag in range(-(size - 1), size):
            self._recompute_diag(diag)
            self._recompute_anti(diag)

    def _update_affected_lines(self, x: int, y: int, stone: int) -> None:
        self._recompute_row(y)
        self._recompute_col(x)
        self._recompute_diag(x - y)
        self._recompute_anti(x + y - (self.board.size - 1))

    def _recompute_row(self, y: int) -> None:
        cells = [self.board.get(x, y) for x in range(self.board.size)]
        key = ("row", y)
        self.line_codes[key] = PatternEvaluator.encode_window(cells)
        self.pattern_cache[key] = PatternEvaluator.classify_cells(cells, BLACK)

    def _recompute_col(self, x: int) -> None:
        cells = [self.board.get(x, y) for y in range(self.board.size)]
        key = ("col", x)
        self.line_codes[key] = PatternEvaluator.encode_window(cells)
        self.pattern_cache[key] = PatternEvaluator.classify_cells(cells, BLACK)

    def _recompute_diag(self, d: int) -> None:
        # x - y = d
        cells: List[int] = []
        for x in range(self.board.size):
            y = x - d
            if 0 <= y < self.board.size:
                cells.append(self.board.get(x, y))
        key = ("diag", d)
        self.line_codes[key] = PatternEvaluator.encode_window(cells) if cells else 0
        self.pattern_cache[key] = PatternEvaluator.classify_cells(cells, BLACK) if cells else PatternType.NONE

    def _recompute_anti(self, s: int) -> None:
        # x + y = s + size - 1
        total = s + self.board.size - 1
        cells: List[int] = []
        for x in range(self.board.size):
            y = total - x
            if 0 <= y < self.board.size:
                cells.append(self.board.get(x, y))
        key = ("anti", s)
        self.line_codes[key] = PatternEvaluator.encode_window(cells) if cells else 0
        self.pattern_cache[key] = PatternEvaluator.classify_cells(cells, BLACK) if cells else PatternType.NONE


class VCFSolver:
    def __init__(self, max_nodes: int = 2000, max_width_attack: int = 10, max_width_defense: int = 12) -> None:
        self.nodes = 0
        self.max_nodes = max(200, max_nodes)
        self.max_width_attack = max(2, max_width_attack)
        self.max_width_defense = max(2, max_width_defense)
        self._tt: Dict[Tuple[Tuple[Tuple[int, ...], ...], int, int], ThreatResultType] = {}

    def solve(self, position: GameBoard, attacker: int, max_depth: int = 6) -> ThreatResult:
        self.nodes = 0
        self._tt.clear()
        outcome, pv = self._dfs(position, attacker, attacker, max_depth, [])
        return ThreatResult(result=outcome, pv=pv, nodes=self.nodes)

    def _dfs(
        self,
        board: GameBoard,
        attacker: int,
        current: int,
        depth: int,
        pv: List[Tuple[int, int]],
    ) -> Tuple[ThreatResultType, List[Tuple[int, int]]]:
        self.nodes += 1
        if self.nodes > self.max_nodes:
            return ThreatResultType.UNKNOWN, pv
        tt_key = (board.state_key(), current, depth)
        cached = self._tt.get(tt_key)
        if cached is not None:
            return cached, pv
        if depth <= 0:
            self._tt[tt_key] = ThreatResultType.UNKNOWN
            return ThreatResultType.UNKNOWN, pv
        if board.winner == attacker:
            self._tt[tt_key] = ThreatResultType.WIN
            return ThreatResultType.WIN, pv
        if board.winner == opponent(attacker):
            self._tt[tt_key] = ThreatResultType.LOSS
            return ThreatResultType.LOSS, pv

        if current == attacker:
            threats = self._attacker_threat_moves(board, attacker)
            if not threats:
                self._tt[tt_key] = ThreatResultType.UNKNOWN
                return ThreatResultType.UNKNOWN, pv
            for x, y in threats:
                board.place(x, y, attacker)
                result, child_pv = self._dfs(board, attacker, opponent(attacker), depth - 1, pv + [(x, y)])
                board.remove(x, y)
                if result == ThreatResultType.WIN:
                    self._tt[tt_key] = ThreatResultType.WIN
                    return result, child_pv
            self._tt[tt_key] = ThreatResultType.UNKNOWN
            return ThreatResultType.UNKNOWN, pv

        defenses = self._defender_responses(board, attacker)
        if not defenses:
            self._tt[tt_key] = ThreatResultType.WIN
            return ThreatResultType.WIN, pv
        for x, y in defenses:
            stone = opponent(attacker)
            board.place(x, y, stone)
            result, child_pv = self._dfs(board, attacker, attacker, depth - 1, pv + [(x, y)])
            board.remove(x, y)
            if result != ThreatResultType.WIN:
                final = ThreatResultType.LOSS if result == ThreatResultType.LOSS else ThreatResultType.UNKNOWN
                self._tt[tt_key] = final
                return final, child_pv
        self._tt[tt_key] = ThreatResultType.WIN
        return ThreatResultType.WIN, pv

    def _attacker_threat_moves(self, board: GameBoard, stone: int) -> List[Tuple[int, int]]:
        scored: List[Tuple[int, int, int]] = []
        for move in board.focused_candidate_moves(distance=3, limit_area=6):
            if board.get(move.x, move.y) != EMPTY:
                continue
            board.place(move.x, move.y, stone)
            win_now = board.winner == stone
            patterns = PatternEvaluator.classify_directions(board, move.x, move.y, stone)
            level = PatternEvaluator.classify_threat(patterns)
            board.remove(move.x, move.y)
            if win_now or level in (ThreatLevel.WIN, ThreatLevel.MUST_BLOCK):
                priority = 2 if win_now or level == ThreatLevel.WIN else 1
                scored.append((priority, move.x, move.y))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [(x, y) for _p, x, y in scored[: self.max_width_attack]]

    def _defender_responses(self, board: GameBoard, attacker: int) -> List[Tuple[int, int]]:
        # Defender must block attacker's direct winning points first.
        wins = sorted(board.immediate_winning_points(attacker, limit=20))
        if wins:
            return wins[: self.max_width_defense]
        # Or block open-four endpoints generated by attacker's strong moves.
        candidate: set[Tuple[int, int]] = set()
        for move in board.focused_candidate_moves(distance=2, limit_area=6):
            if board.get(move.x, move.y) != EMPTY:
                continue
            board.place(move.x, move.y, attacker)
            if board.winner == attacker:
                board.remove(move.x, move.y)
                candidate.add((move.x, move.y))
                continue
            for block in board.immediate_winning_points(attacker, limit=6):
                candidate.add(block)
            board.remove(move.x, move.y)
        return sorted(candidate)[: self.max_width_defense]


class VCTSolver(VCFSolver):
    def _attacker_threat_moves(self, board: GameBoard, stone: int) -> List[Tuple[int, int]]:
        scored: List[Tuple[int, int, int]] = []
        for move in board.focused_candidate_moves(distance=3, limit_area=8):
            if board.get(move.x, move.y) != EMPTY:
                continue
            board.place(move.x, move.y, stone)
            win_now = board.winner == stone
            patterns = PatternEvaluator.classify_directions(board, move.x, move.y, stone)
            level = PatternEvaluator.classify_threat(patterns)
            forcing_count = sum(1 for p in patterns if p in (PatternType.OPEN_THREE, PatternType.OPEN_FOUR, PatternType.FOUR))
            board.remove(move.x, move.y)
            if win_now or level in (ThreatLevel.WIN, ThreatLevel.MUST_BLOCK):
                priority = 3 if win_now or level == ThreatLevel.WIN else 2
                scored.append((priority, move.x, move.y))
            elif level == ThreatLevel.FORCING and forcing_count >= 2:
                # double-threat candidate
                scored.append((1, move.x, move.y))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [(x, y) for _p, x, y in scored[: self.max_width_attack]]


class ForbiddenChecker:
    def __init__(self, size: int = 15) -> None:
        self.state = StateUpdater(size=size)
        self._hits = 0
        self._misses = 0
        self._cache: Dict[Tuple[int, int, int, int], bool] = {}

    def load_from_board(self, board: GameBoard) -> None:
        self.state.board.reset()
        for x, y, stone in board.history:
            self.state.make_move(Move(x, y), stone)
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def is_forbidden(self, x: int, y: int, stone: int) -> bool:
        from gomoku_core import forbidden_reason

        board_hash, _state = self.state.snapshot_key()
        key = (board_hash, x, y, stone)
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        result = forbidden_reason(self.state.board, x, y, stone) is not None
        self._cache[key] = result
        return result

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return (self._hits / float(total)) if total > 0 else 0.0


class ParallelSearch:
    def __init__(self, threads: int = 2, depth_offset: int = 1) -> None:
        self.threads = max(2, threads)
        self.depth_offset = max(0, depth_offset)

    @staticmethod
    def _clone_board(board: GameBoard) -> GameBoard:
        clone = GameBoard(size=board.size)
        for x, y, stone in board.history:
            clone.place(x, y, stone)
        return clone

    def best_move(
        self,
        board: GameBoard,
        stone: int,
        ai_builder: Callable[[int], "GomokuAI"],
    ) -> Optional[Move]:
        candidates = board.focused_candidate_moves(distance=2, limit_area=8)
        if not candidates:
            candidates = board.candidate_moves()
        if not candidates:
            return None
        random.shuffle(candidates)
        root_moves = candidates[: min(len(candidates), self.threads * 2)]
        if not root_moves:
            return None

        from gomoku_core import GomokuAI

        best: Optional[Move] = None
        best_score = -10**18
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = []
            for idx, move in enumerate(root_moves):
                local_board = self._clone_board(board)
                depth_shift = idx % (self.depth_offset + 1)
                local_ai = ai_builder(depth_shift)
                futures.append(pool.submit(self._score_move, local_board, stone, move, local_ai))
            for fut in as_completed(futures):
                scored = fut.result()
                if scored is None:
                    continue
                if scored.score > best_score:
                    best_score = scored.score
                    best = scored
        return best

    @staticmethod
    def _score_move(board: GameBoard, stone: int, move: Move, ai: "GomokuAI") -> Optional[Move]:
        if not board.is_inside(move.x, move.y) or board.get(move.x, move.y) != EMPTY:
            return None
        if hasattr(ai, "_is_legal_move") and not ai._is_legal_move(board, move.x, move.y, stone):  # type: ignore[attr-defined]
            return None
        board.place(move.x, move.y, stone)
        score = ai.WIN_SCORE if board.winner == stone else ai.evaluate_board(board, stone)
        board.remove(move.x, move.y)
        return Move(move.x, move.y, score)


class OpeningBook:
    def __init__(self) -> None:
        self.book: Dict[Tuple[Tuple[int, int, int], ...], Tuple[int, int]] = {
            (): (7, 7),
            ((7, 7, BLACK),): (7, 8),
            ((7, 7, BLACK), (7, 8, WHITE)): (8, 7),
            ((7, 7, BLACK), (8, 8, WHITE)): (6, 6),
        }

    def query(self, board: GameBoard, stone: int) -> Optional[Move]:
        if board.move_count > 8:
            return None
        key = tuple(board.history)
        xy = self.book.get(key)
        if xy is None:
            return None
        x, y = xy
        if not board.is_inside(x, y) or board.get(x, y) != EMPTY:
            return None
        return Move(x, y)
