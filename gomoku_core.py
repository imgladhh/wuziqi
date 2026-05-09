from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple


EMPTY = 0
BLACK = 1
WHITE = 2

DIRECTIONS: Sequence[Tuple[int, int]] = ((1, 0), (0, 1), (1, 1), (1, -1))


@dataclass
class Move:
    x: int
    y: int
    score: int = 0


@dataclass
class TTEntry:
    score: int
    flag: int
    depth: int


@dataclass(frozen=True)
class SegmentLineEntry:
    black_score: int
    white_score: int
    black_counts: Tuple[int, int, int, int]
    white_counts: Tuple[int, int, int, int]


@dataclass(frozen=True)
class SegmentCoreState:
    raw_black: int
    raw_white: int
    score_black: int
    score_white: int
    black_counts: Tuple[int, int, int, int]
    white_counts: Tuple[int, int, int, int]
    line_entries: Tuple[SegmentLineEntry, ...]


def _decode_base3(code: int, width: int = 9) -> List[int]:
    cells = [0] * width
    for index in range(width - 1, -1, -1):
        cells[index] = code % 3
        code //= 3
    return cells


def _line_pattern_from_window(cells: Sequence[int]) -> Tuple[int, int]:
    center = len(cells) // 2
    if cells[center] != 1:
        return 0, 0

    count = 1
    left = center - 1
    while left >= 0 and cells[left] == 1:
        count += 1
        left -= 1

    right = center + 1
    while right < len(cells) and cells[right] == 1:
        count += 1
        right += 1

    open_ends = 0
    if left >= 0 and cells[left] == EMPTY:
        open_ends += 1
    if right < len(cells) and cells[right] == EMPTY:
        open_ends += 1
    return count, open_ends


def _build_line_pattern_tables(win_score: int) -> Dict[str, List[int]]:
    phase_tables = {
        "opening": {
            (4, 2): 180_000,
            (4, 1): 45_000,
            (3, 2): 22_000,
            (3, 1): 4_500,
            (2, 2): 1_600,
            (2, 1): 360,
            (1, 2): 100,
        },
        "middle": {
            (4, 2): 240_000,
            (4, 1): 62_000,
            (3, 2): 28_000,
            (3, 1): 6_200,
            (2, 2): 1_500,
            (2, 1): 360,
            (1, 2): 90,
        },
        "ending": {
            (4, 2): 280_000,
            (4, 1): 75_000,
            (3, 2): 20_000,
            (3, 1): 5_400,
            (2, 2): 1_200,
            (2, 1): 320,
            (1, 2): 70,
        },
    }
    out: Dict[str, List[int]] = {phase: [0] * (3**9) for phase in phase_tables}
    for code in range(3**9):
        count, open_ends = _line_pattern_from_window(_decode_base3(code))
        for phase, table in phase_tables.items():
            if count >= 5:
                out[phase][code] = win_score
            else:
                out[phase][code] = table.get((count, open_ends), 10)
    return out


def _window_has_five(cells: Sequence[int]) -> bool:
    run = 0
    for cell in cells:
        run = run + 1 if cell == 1 else 0
        if run >= 5:
            return True
    return False


def _window_winning_points(cells: Sequence[int]) -> set[int]:
    points: set[int] = set()
    mutable = list(cells)
    for index, cell in enumerate(cells):
        if cell != EMPTY:
            continue
        mutable[index] = 1
        if _window_has_five(mutable):
            points.add(index)
        mutable[index] = EMPTY
    return points


def _window_open_three_moves(cells: Sequence[int]) -> set[int]:
    moves: set[int] = set()
    mutable = list(cells)
    for index, cell in enumerate(cells):
        if cell != EMPTY:
            continue
        mutable[index] = 1
        if len(_window_winning_points(mutable)) >= 2:
            moves.add(index)
        mutable[index] = EMPTY
    return moves


def _window_minor_shape_score(cells: Sequence[int], phase: str) -> int:
    open_two = 0
    blocked_three = 0
    index = 0
    while index < len(cells):
        if cells[index] != 1:
            index += 1
            continue
        start = index
        while index < len(cells) and cells[index] == 1:
            index += 1
        length = index - start
        left_open = start > 0 and cells[start - 1] == EMPTY
        right_open = index < len(cells) and cells[index] == EMPTY
        open_ends = int(left_open) + int(right_open)
        if length == 3 and open_ends == 1:
            blocked_three += 1
        elif length == 2 and open_ends == 2:
            open_two += 1
    if phase == "opening":
        return open_two * 1_200 + blocked_three * 2_800
    if phase == "ending":
        return open_two * 900 + blocked_three * 3_200
    return open_two * 1_000 + blocked_three * 3_000


def _phase_four_score(phase: str) -> int:
    if phase == "opening":
        return 45_000
    if phase == "ending":
        return 75_000
    return 62_000


def _phase_open_three_score(phase: str) -> int:
    if phase == "opening":
        return 22_000
    if phase == "ending":
        return 20_000
    return 28_000


def _segment_window_entry(cells: Sequence[int], phase: str, win_score: int) -> Tuple[int, int, int, int, int]:
    if _window_has_five(cells):
        return win_score, 0, 0, 0, 1

    score = 0
    open_three = 0
    four = 0
    open_four = 0
    win_points = _window_winning_points(cells)
    if len(win_points) >= 2:
        open_four = len(win_points)
        score += 780_000 + (len(win_points) - 2) * 120_000
    elif len(win_points) == 1:
        four = 1
        score += _phase_four_score(phase)

    open_three_moves = _window_open_three_moves(cells)
    open_three = len(open_three_moves)
    if open_three == 1:
        score += _phase_open_three_score(phase)
    elif open_three >= 2:
        score += 120_000 + (open_three - 2) * 35_000

    score += _window_minor_shape_score(cells, phase)
    return score, open_three, four, open_four, 0


def _build_segment_window_tables(win_score: int) -> Dict[str, List[Tuple[int, int, int, int, int]]]:
    tables: Dict[str, List[Tuple[int, int, int, int, int]]] = {
        "opening": [(0, 0, 0, 0, 0)] * (3**9),
        "middle": [(0, 0, 0, 0, 0)] * (3**9),
        "ending": [(0, 0, 0, 0, 0)] * (3**9),
    }
    for code in range(3**9):
        cells = _decode_base3(code)
        for phase in tables:
            tables[phase][code] = _segment_window_entry(cells, phase, win_score)
    return tables


class GameBoard:
    def __init__(self, size: int = 15) -> None:
        self.size = size
        self.cells: List[List[int]] = [[EMPTY for _ in range(size)] for _ in range(size)]
        self.move_count = 0
        self.winner = EMPTY
        self.history: List[Tuple[int, int, int]] = []

    def reset(self) -> None:
        for x in range(self.size):
            for y in range(self.size):
                self.cells[x][y] = EMPTY
        self.move_count = 0
        self.winner = EMPTY
        self.history.clear()

    def is_inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def get(self, x: int, y: int) -> int:
        return self.cells[x][y]

    def place(self, x: int, y: int, stone: int) -> bool:
        if not self.is_inside(x, y) or stone == EMPTY or self.cells[x][y] != EMPTY or self.is_game_over:
            return False
        self.cells[x][y] = stone
        self.move_count += 1
        self.history.append((x, y, stone))
        if self.has_five(x, y, stone):
            self.winner = stone
        return True

    def remove(self, x: int, y: int) -> None:
        if self.cells[x][y] == EMPTY:
            return
        stone = self.cells[x][y]
        self.cells[x][y] = EMPTY
        self.move_count = max(0, self.move_count - 1)
        self.winner = EMPTY
        if self.history and self.history[-1] == (x, y, stone):
            self.history.pop()
            return
        for index in range(len(self.history) - 1, -1, -1):
            if self.history[index] == (x, y, stone):
                self.history.pop(index)
                break

    def undo_last(self) -> Optional[Tuple[int, int, int]]:
        if not self.history:
            return None
        x, y, stone = self.history[-1]
        self.remove(x, y)
        return x, y, stone

    @property
    def is_game_over(self) -> bool:
        return self.winner != EMPTY or self.move_count >= self.size * self.size

    def has_five(self, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            total = 1 + self._count_direction(x, y, dx, dy, stone) + self._count_direction(x, y, -dx, -dy, stone)
            if total >= 5:
                return True
        return False

    def has_overline(self, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            total = 1 + self._count_direction(x, y, dx, dy, stone) + self._count_direction(x, y, -dx, -dy, stone)
            if total >= 6:
                return True
        return False

    def _count_direction(self, x: int, y: int, dx: int, dy: int, stone: int) -> int:
        count = 0
        cx, cy = x + dx, y + dy
        while self.is_inside(cx, cy) and self.cells[cx][cy] == stone:
            count += 1
            cx += dx
            cy += dy
        return count

    def has_neighbor(self, x: int, y: int, distance: int = 2) -> bool:
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if self.is_inside(nx, ny) and self.cells[nx][ny] != EMPTY:
                    return True
        return False

    def candidate_moves(self) -> List[Move]:
        if self.move_count == 0:
            center = self.size // 2
            return [Move(center, center)]

        moves: List[Move] = []
        min_x, max_x, min_y, max_y = self.occupied_bounds(padding=2)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                if self.cells[x][y] == EMPTY and self.has_neighbor(x, y):
                    moves.append(Move(x, y))
        return moves

    def focused_candidate_moves(self, distance: int = 2, limit_area: int = 2) -> List[Move]:
        if self.move_count == 0:
            center = self.size // 2
            return [Move(center, center)]

        recent = self.history[-limit_area:] if self.history else []
        if not recent:
            return self.candidate_moves()

        seen: set[Tuple[int, int]] = set()
        moves: List[Move] = []
        for x, y, _stone in recent:
            for dx in range(-distance, distance + 1):
                for dy in range(-distance, distance + 1):
                    nx, ny = x + dx, y + dy
                    if not self.is_inside(nx, ny) or self.cells[nx][ny] != EMPTY:
                        continue
                    if (nx, ny) in seen or not self.has_neighbor(nx, ny, distance):
                        continue
                    seen.add((nx, ny))
                    moves.append(Move(nx, ny))
        if moves:
            return moves
        return self.candidate_moves()

    def state_key(self) -> Tuple[Tuple[int, ...], ...]:
        return tuple(tuple(row) for row in self.cells)

    def occupied_bounds(self, padding: int = 1) -> Tuple[int, int, int, int]:
        if not self.history:
            return 0, self.size - 1, 0, self.size - 1

        xs = [x for x, _y, _stone in self.history]
        ys = [y for _x, y, _stone in self.history]
        min_x = max(0, min(xs) - padding)
        max_x = min(self.size - 1, max(xs) + padding)
        min_y = max(0, min(ys) - padding)
        max_y = min(self.size - 1, max(ys) + padding)
        return min_x, max_x, min_y, max_y

    def immediate_winning_points(self, stone: int, limit: Optional[int] = None) -> List[Tuple[int, int]]:
        points: List[Tuple[int, int]] = []
        for move in self.candidate_moves():
            self.place(move.x, move.y, stone)
            is_win = self.winner == stone
            self.remove(move.x, move.y)
            if is_win:
                points.append((move.x, move.y))
                if limit is not None and len(points) >= limit:
                    break
        return points

    def straight_four_points(self, stone: int, limit: Optional[int] = None) -> List[Tuple[int, int]]:
        points: List[Tuple[int, int]] = []
        for move in self.candidate_moves():
            self.place(move.x, move.y, stone)
            makes_straight_four = self._move_makes_straight_four(move.x, move.y, stone)
            self.remove(move.x, move.y)
            if makes_straight_four:
                points.append((move.x, move.y))
                if limit is not None and len(points) >= limit:
                    break
        return points

    def _move_makes_straight_four(self, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count_pos = self._count_direction(x, y, dx, dy, stone)
            count_neg = self._count_direction(x, y, -dx, -dy, stone)
            total = 1 + count_pos + count_neg
            if total != 4:
                continue
            end_pos_x = x + (count_pos + 1) * dx
            end_pos_y = y + (count_pos + 1) * dy
            end_neg_x = x - (count_neg + 1) * dx
            end_neg_y = y - (count_neg + 1) * dy
            open_pos = self.is_inside(end_pos_x, end_pos_y) and self.get(end_pos_x, end_pos_y) == EMPTY
            open_neg = self.is_inside(end_neg_x, end_neg_y) and self.get(end_neg_x, end_neg_y) == EMPTY
            if open_pos and open_neg:
                return True
        return False


def forbidden_reason(board: GameBoard, x: int, y: int, stone: int) -> Optional[str]:
    if stone != BLACK:
        return None
    if not board.is_inside(x, y) or board.get(x, y) != EMPTY:
        return None

    board.place(x, y, BLACK)
    try:
        if board.has_overline(x, y, BLACK):
            return "overline"

        # Renju: direct five is legal for black unless it is overline.
        if board.winner == BLACK:
            return None

        if _count_live_four_threats(board, x, y, BLACK) >= 2:
            return "double_four"

        if _count_open_three_directions(board, x, y, BLACK) >= 2:
            return "double_three"
    finally:
        board.remove(x, y)
    return None


def is_forbidden_move(board: GameBoard, x: int, y: int, stone: int) -> bool:
    return forbidden_reason(board, x, y, stone) is not None


def _line_points(
    board: GameBoard,
    x: int,
    y: int,
    dx: int,
    dy: int,
    radius: int = 5,
) -> List[Tuple[int, int]]:
    points: List[Tuple[int, int]] = []
    for offset in range(-radius, radius + 1):
        points.append((x + offset * dx, y + offset * dy))
    return points


def _line_chars(
    board: GameBoard,
    points: Sequence[Tuple[int, int]],
    stone: int,
) -> List[str]:
    chars: List[str] = []
    for px, py in points:
        if not board.is_inside(px, py):
            chars.append("#")
            continue
        cell = board.get(px, py)
        if cell == EMPTY:
            chars.append(".")
        elif cell == stone:
            chars.append("S")
        else:
            chars.append("#")
    return chars


def _live_four_windows_in_direction(
    board: GameBoard,
    x: int,
    y: int,
    dx: int,
    dy: int,
    stone: int,
) -> List[frozenset[Tuple[int, int]]]:
    points = _line_points(board, x, y, dx, dy, radius=5)
    chars = _line_chars(board, points, stone)
    center_index = len(points) // 2
    windows: List[frozenset[Tuple[int, int]]] = []

    for start in range(0, len(chars) - 5):
        if chars[start] != "." or chars[start + 5] != ".":
            continue
        segment = chars[start + 1 : start + 5]
        if any(ch != "S" for ch in segment):
            continue
        if not (start + 1 <= center_index <= start + 4):
            continue
        stones = frozenset(points[start + 1 : start + 5])
        windows.append(stones)
    return windows


def _count_live_four_threats(board: GameBoard, x: int, y: int, stone: int) -> int:
    unique: set[frozenset[Tuple[int, int]]] = set()
    for dx, dy in DIRECTIONS:
        for window in _live_four_windows_in_direction(board, x, y, dx, dy, stone):
            if (x, y) in window:
                unique.add(window)
    return len(unique)


def _is_open_three_in_direction(board: GameBoard, x: int, y: int, dx: int, dy: int, stone: int) -> bool:
    # Strict Renju-style open three:
    # there exists one extension move on this line that creates a live four.
    points = _line_points(board, x, y, dx, dy, radius=4)
    for ex, ey in points:
        if not board.is_inside(ex, ey) or board.get(ex, ey) != EMPTY:
            continue
        board.place(ex, ey, stone)
        try:
            if board.has_overline(ex, ey, stone):
                continue
            windows = _live_four_windows_in_direction(board, x, y, dx, dy, stone)
            if any((x, y) in window and (ex, ey) in window for window in windows):
                return True
        finally:
            board.remove(ex, ey)
    return False


def _count_open_three_directions(board: GameBoard, x: int, y: int, stone: int) -> int:
    total = 0
    for dx, dy in DIRECTIONS:
        if _is_open_three_in_direction(board, x, y, dx, dy, stone):
            total += 1
    return total


def opponent(stone: int) -> int:
    return WHITE if stone == BLACK else BLACK


class GomokuAI:
    TT_EXACT = 0
    TT_LOWER = 1
    TT_UPPER = 2
    WIN_SCORE = 10_000_000
    FORCE_SCORE = WIN_SCORE // 2
    DEFAULT_TIME_LIMIT_MS = 1200
    MOVE_CANDIDATE_LIMIT = 14
    QUIESCENCE_MAX_PLY = 5
    LMR_MIN_DEPTH = 3
    LMR_MIN_INDEX = 4
    ENEMY_THREAT_PENALTY_SCALE = 1.35
    ENEMY_MAJOR_THREAT_PENALTY = 42_000
    ENEMY_OPEN_FOUR_PENALTY = 160_000
    ENEMY_WIN_POINT_PENALTY = 420_000
    OWN_OPEN_FOUR_BONUS = 85_000
    OWN_WIN_POINT_BONUS = 170_000
    TIER_OWN_FIVE = 0
    TIER_BLOCK_ENEMY_FIVE = 1
    TIER_BLOCK_ENEMY_OPEN_FOUR = 2
    TIER_BLOCK_ENEMY_COMBO = 3
    TIER_OWN_FOUR_THREAT = 3
    TIER_OWN_DOUBLE_THREE = 4
    TIER_NORMAL = 5
    _LINE_PATTERN_TABLES: Dict[str, List[int]] = {}
    _SEGMENT_WINDOW_TABLES: Dict[str, List[Tuple[int, int, int, int, int]]] = {}
    _SEGMENT_GEOMETRY_CACHE: Dict[int, Tuple[Tuple[Tuple[Tuple[int, int], ...], ...], Dict[Tuple[int, int], Tuple[int, ...]]]] = {}

    def __init__(
        self,
        depth: int = 3,
        legal_move_checker: Optional[Callable[[GameBoard, int, int, int], bool]] = None,
        time_limit_ms: Optional[int] = None,
        use_pvs: bool = True,
        use_quiescence: bool = True,
        use_threat_space: bool = True,
        opening_move_provider: Optional[Callable[[GameBoard, int], Optional[Move]]] = None,
        use_opening_book: bool = True,
        use_vcf_probe: bool = True,
        vcf_probe_depth: int = 6,
        use_vct_probe: bool = True,
        vct_probe_depth: int = 8,
        use_pattern_lookup: bool = True,
        use_line_pattern_lookup: bool = False,
        use_aspiration: bool = True,
        aspiration_delta: int = 120,
        use_iid: bool = True,
        iid_min_depth: int = 5,
        use_lmr: bool = True,
        use_c_engine: bool = False,
        use_incremental_core_eval: bool = True,
        use_segment_core_eval: bool = False,
        use_eval_correction: bool = True,
        eval_correction_limit: float = 0.10,
        use_threat_qsearch: bool = True,
        use_lazy_smp: bool = True,
        smp_threads: int = 2,
        smp_depth_offset: int = 1,
        use_defense_urgency: bool = True,
        enemy_threat_penalty_scale: float = ENEMY_THREAT_PENALTY_SCALE,
        enemy_pattern_scale: float = 1.0,
        score_open_four: int = 240_000,
        score_half_four: int = 62_000,
        score_open_three: int = 28_000,
        score_half_three: int = 6_200,
        score_open_two: int = 1_500,
        score_half_two: int = 360,
        own_win_point_bonus: int = OWN_WIN_POINT_BONUS,
        enemy_win_point_penalty: int = ENEMY_WIN_POINT_PENALTY,
        own_open_four_bonus: int = OWN_OPEN_FOUR_BONUS,
        enemy_open_four_penalty: int = ENEMY_OPEN_FOUR_PENALTY,
        enemy_major_threat_penalty: int = ENEMY_MAJOR_THREAT_PENALTY,
        vcf_max_nodes: int = 1800,
        vcf_max_width_attack: int = 8,
        vcf_max_width_defense: int = 10,
        vct_max_nodes: int = 2500,
        vct_max_width_attack: int = 10,
        vct_max_width_defense: int = 12,
    ) -> None:
        self.depth = max(1, depth)
        self.time_limit_ms = time_limit_ms
        self.use_pvs = use_pvs
        self.use_quiescence = use_quiescence
        self.use_threat_space = use_threat_space
        self.use_opening_book = use_opening_book
        self.use_vcf_probe = use_vcf_probe
        self.vcf_probe_depth = max(2, vcf_probe_depth)
        self.use_vct_probe = use_vct_probe
        self.vct_probe_depth = max(3, vct_probe_depth)
        self.use_pattern_lookup = use_pattern_lookup
        self.use_line_pattern_lookup = use_line_pattern_lookup
        self.use_aspiration = use_aspiration
        self.aspiration_delta = max(40, aspiration_delta)
        self.use_iid = use_iid
        self.iid_min_depth = max(3, iid_min_depth)
        self.use_lmr = use_lmr
        self.use_c_engine = use_c_engine
        self.use_incremental_core_eval = use_incremental_core_eval
        self.use_segment_core_eval = use_segment_core_eval
        self.use_eval_correction = use_eval_correction
        self.eval_correction_limit = max(0.01, min(0.50, eval_correction_limit))
        self.use_threat_qsearch = use_threat_qsearch
        self.use_lazy_smp = use_lazy_smp
        self.smp_threads = max(2, smp_threads)
        self.smp_depth_offset = max(0, smp_depth_offset)
        self.use_defense_urgency = use_defense_urgency
        self.enemy_threat_penalty_scale = max(0.5, min(2.5, enemy_threat_penalty_scale))
        self.enemy_pattern_scale = max(0.5, min(3.0, enemy_pattern_scale))
        self.pattern_scores = {
            "opening": {
                (4, 2): 180_000,
                (4, 1): 45_000,
                (3, 2): 22_000,
                (3, 1): 4_500,
                (2, 2): 1_600,
                (2, 1): 360,
                (1, 2): 100,
            },
            "middle": {
                (4, 2): max(1, int(score_open_four)),
                (4, 1): max(1, int(score_half_four)),
                (3, 2): max(1, int(score_open_three)),
                (3, 1): max(1, int(score_half_three)),
                (2, 2): max(1, int(score_open_two)),
                (2, 1): max(1, int(score_half_two)),
                (1, 2): 90,
            },
            "ending": {
                (4, 2): 280_000,
                (4, 1): 75_000,
                (3, 2): 20_000,
                (3, 1): 5_400,
                (2, 2): 1_200,
                (2, 1): 320,
                (1, 2): 70,
            },
        }
        self.own_win_point_bonus = max(0, int(own_win_point_bonus))
        self.enemy_win_point_penalty = max(0, int(enemy_win_point_penalty))
        self.own_open_four_bonus = max(0, int(own_open_four_bonus))
        self.enemy_open_four_penalty = max(0, int(enemy_open_four_penalty))
        self.enemy_major_threat_penalty = max(0, int(enemy_major_threat_penalty))
        self.vcf_max_nodes = max(300, vcf_max_nodes)
        self.vcf_max_width_attack = max(2, vcf_max_width_attack)
        self.vcf_max_width_defense = max(2, vcf_max_width_defense)
        self.vct_max_nodes = max(400, vct_max_nodes)
        self.vct_max_width_attack = max(2, vct_max_width_attack)
        self.vct_max_width_defense = max(2, vct_max_width_defense)
        self.opening_move_provider = opening_move_provider
        self._legal_move_checker = legal_move_checker
        self._tt: Dict[Tuple[int, bool, int, int], TTEntry] = {}
        self._move_score_cache: Dict[Tuple[int, int, int, Tuple[Tuple[int, int], ...]], List[Move]] = {}
        self._history_table: Dict[Tuple[int, int, int], int] = {}
        self._killer_moves: Dict[int, List[Tuple[int, int]]] = {}
        self._zobrist_table: List[List[Tuple[int, int]]] = []
        self._zobrist_size = 0
        self._deadline = 0.0
        self._iterative_depth = self.depth
        self._default_opening_provider: Optional[Callable[[GameBoard, int], Optional[Move]]] = None

    def best_move(self, board: GameBoard, ai_stone: int) -> Move:
        self._tt.clear()
        self._move_score_cache.clear()
        self._killer_moves.clear()
        self._ensure_zobrist(board.size)
        opening_provider = self._resolve_opening_provider()
        if opening_provider is not None and board.move_count <= 8 and self.use_opening_book:
            opening = opening_provider(board, ai_stone)
            if opening is not None and self._is_legal_move(board, opening.x, opening.y, ai_stone):
                if board.is_inside(opening.x, opening.y) and board.get(opening.x, opening.y) == EMPTY:
                    return Move(opening.x, opening.y)
        limit_ms = self.time_limit_ms if self.time_limit_ms is not None else self.DEFAULT_TIME_LIMIT_MS

        c_move = self._c_engine_move(board, ai_stone, limit_ms)
        if c_move is not None:
            return c_move

        self._deadline = time.perf_counter() + max(0.15, limit_ms / 1000.0)

        forced = self._forced_move(board, ai_stone)
        if forced is not None:
            return forced

        if self.use_vcf_probe and self._should_trigger_vcf_probe(board, ai_stone):
            vcf_move = self._vcf_probe_root(board, ai_stone)
            if vcf_move is not None and self._is_legal_move(board, vcf_move.x, vcf_move.y, ai_stone):
                return vcf_move
        if self.use_vct_probe and self._should_trigger_vct_probe(board, ai_stone):
            vct_move = self._vct_probe_root(board, ai_stone)
            if vct_move is not None and self._is_legal_move(board, vct_move.x, vct_move.y, ai_stone):
                return vct_move

        combo_defense = self._find_combo_threat_response(board, ai_stone)
        if combo_defense is not None:
            return combo_defense

        if self.use_lazy_smp and self.smp_threads > 1 and board.move_count >= 6:
            smp_move = self._lazy_smp_root(board, ai_stone)
            if smp_move is not None and self._is_legal_move(board, smp_move.x, smp_move.y, ai_stone):
                return smp_move

        best: Optional[Move] = None
        prev_score = 0
        for depth in range(1, self.depth + 1):
            self._iterative_depth = depth
            try:
                if self.use_aspiration and depth >= 2:
                    delta = self.aspiration_delta
                    candidate: Optional[Move] = None
                    while True:
                        low = prev_score - delta
                        high = prev_score + delta
                        candidate, score = self._search_root(board, ai_stone, depth, alpha=low, beta=high)
                        if candidate is None:
                            break
                        if score <= low:
                            delta *= 2
                            if delta > self.WIN_SCORE:
                                break
                            continue
                        if score >= high:
                            delta *= 2
                            if delta > self.WIN_SCORE:
                                break
                            continue
                        prev_score = score
                        break
                    if candidate is None:
                        candidate, score = self._search_root(board, ai_stone, depth)
                        if candidate is not None:
                            prev_score = score
                else:
                    candidate, score = self._search_root(board, ai_stone, depth)
                    if candidate is not None:
                        prev_score = score
            except TimeoutError:
                break
            if candidate is not None:
                best = candidate
            if self._time_up():
                break
        if best is not None:
            return best

        for move in board.candidate_moves():
            if self._is_legal_move(board, move.x, move.y, ai_stone):
                return Move(move.x, move.y)
        return Move(board.size // 2, board.size // 2)

    def _c_engine_move(self, board: GameBoard, ai_stone: int, limit_ms: int) -> Optional[Move]:
        if not self.use_c_engine:
            return None
        if board.size != 15:
            return None
        competitive = self._legal_move_checker is not None
        try:
            from engine_c.c_bridge import c_best_move
        except Exception:
            return None
        weights = {
            "score_open_four": self.pattern_scores["middle"][(4, 2)],
            "score_half_four": self.pattern_scores["middle"][(4, 1)],
            "score_open_three": self.pattern_scores["middle"][(3, 2)],
            "score_half_three": self.pattern_scores["middle"][(3, 1)],
            "score_open_two": self.pattern_scores["middle"][(2, 2)],
            "score_half_two": self.pattern_scores["middle"][(2, 1)],
            "enemy_scale": self.enemy_pattern_scale,
        }
        try:
            x, y = c_best_move(
                board.cells,
                board.size,
                ai_stone,
                board.move_count,
                self.depth,
                float(limit_ms),
                weights,
                competitive=competitive,
            )
        except Exception:
            return None
        if board.is_inside(x, y) and board.get(x, y) == EMPTY and self._is_legal_move(board, x, y, ai_stone):
            return Move(x, y)
        return None

    def suggest_move(self, board: GameBoard, ai_stone: int) -> Tuple[Move, str]:
        move = self.best_move(board, ai_stone)
        reason = self._explain_move(board, ai_stone, move)
        return move, reason

    def _resolve_opening_provider(self) -> Optional[Callable[[GameBoard, int], Optional[Move]]]:
        if self.opening_move_provider is not None:
            return self.opening_move_provider
        if not self.use_opening_book:
            return None
        if self._default_opening_provider is not None:
            return self._default_opening_provider
        try:
            from engine_p1 import OpeningBook  # local import to avoid circular dependency at module load

            book = OpeningBook()
            self._default_opening_provider = book.query
        except Exception:
            self._default_opening_provider = None
        return self._default_opening_provider

    def _vcf_probe_root(self, board: GameBoard, stone: int) -> Optional[Move]:
        if board.move_count < 6:
            return None
        try:
            from engine_p1 import ThreatResultType, VCFSolver  # local import to avoid circular dependency
        except Exception:
            return None
        solver = VCFSolver(
            max_nodes=self.vcf_max_nodes,
            max_width_attack=self.vcf_max_width_attack,
            max_width_defense=self.vcf_max_width_defense,
        )
        result = solver.solve(board, attacker=stone, max_depth=self.vcf_probe_depth)
        if result.result != ThreatResultType.WIN or not result.pv:
            return None
        x, y = result.pv[0]
        if board.is_inside(x, y) and board.get(x, y) == EMPTY:
            return Move(x, y, self.FORCE_SCORE)
        return None

    def _vct_probe_root(self, board: GameBoard, stone: int) -> Optional[Move]:
        if board.move_count < 8:
            return None
        try:
            from engine_p1 import ThreatResultType, VCTSolver
        except Exception:
            return None
        solver = VCTSolver(
            max_nodes=self.vct_max_nodes,
            max_width_attack=self.vct_max_width_attack,
            max_width_defense=self.vct_max_width_defense,
        )
        result = solver.solve(board, attacker=stone, max_depth=self.vct_probe_depth)
        if result.result != ThreatResultType.WIN or not result.pv:
            return None
        x, y = result.pv[0]
        if board.is_inside(x, y) and board.get(x, y) == EMPTY:
            return Move(x, y, self.FORCE_SCORE // 2)
        return None

    def _should_trigger_vcf_probe(self, board: GameBoard, stone: int) -> bool:
        if board.move_count < 6 or self._time_up():
            return False
        if not board.history:
            return False
        if (self._deadline - time.perf_counter()) < 0.08:
            return False
        enemy = opponent(stone)
        # Root gate: only probe when there is near-term tactical tension.
        if board.immediate_winning_points(stone, limit=1):
            return True
        if board.immediate_winning_points(enemy, limit=1):
            return True
        if self._find_open_four_points(board, stone, limit=1):
            return True
        if self._find_open_four_points(board, enemy, limit=1):
            return True
        if self._find_combo_threat_points(board, enemy, defender=stone, limit=1):
            return True
        lx, ly, ls = board.history[-1]
        return self._move_has_open_three_or_four(board, lx, ly, ls)

    def _should_trigger_vct_probe(self, board: GameBoard, stone: int) -> bool:
        if board.move_count < 8 or not self._should_trigger_vcf_probe(board, stone):
            return False
        if (self._deadline - time.perf_counter()) < 0.12:
            return False
        enemy = opponent(stone)
        # VCT gate: slightly stricter than VCF, require stronger forcing signal.
        if self._find_open_four_points(board, stone, limit=1):
            return True
        if self._find_major_threat_points(board, stone, limit=2):
            return True
        lx, ly, ls = board.history[-1]
        if ls == enemy and self._move_has_open_three_or_four(board, lx, ly, ls):
            return True
        return False

    def _move_has_open_three_or_four(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                return True
            if count == 3 and open_ends == 2:
                return True
        return False

    def _lazy_smp_root(self, board: GameBoard, stone: int) -> Optional[Move]:
        try:
            from engine_p1 import ParallelSearch
        except Exception:
            return None
        parallel = ParallelSearch(threads=self.smp_threads, depth_offset=self.smp_depth_offset)

        def builder(depth_shift: int) -> "GomokuAI":
            # Root workers are intentionally shallowly diversified.
            worker_depth = max(1, self.depth - depth_shift)
            return GomokuAI(
                depth=worker_depth,
                legal_move_checker=self._legal_move_checker,
                time_limit_ms=min(120, self.time_limit_ms or self.DEFAULT_TIME_LIMIT_MS),
                use_pvs=self.use_pvs,
                use_quiescence=self.use_quiescence,
                use_threat_space=self.use_threat_space,
                opening_move_provider=None,
                use_opening_book=False,
                use_vcf_probe=False,
                vcf_probe_depth=self.vcf_probe_depth,
                use_vct_probe=False,
                vct_probe_depth=self.vct_probe_depth,
                use_pattern_lookup=self.use_pattern_lookup,
                use_line_pattern_lookup=self.use_line_pattern_lookup,
                use_aspiration=False,
                aspiration_delta=self.aspiration_delta,
                use_iid=self.use_iid,
                iid_min_depth=self.iid_min_depth,
                use_incremental_core_eval=self.use_incremental_core_eval,
                use_segment_core_eval=self.use_segment_core_eval,
                use_eval_correction=self.use_eval_correction,
                eval_correction_limit=self.eval_correction_limit,
                use_threat_qsearch=self.use_threat_qsearch,
                use_defense_urgency=self.use_defense_urgency,
                enemy_threat_penalty_scale=self.enemy_threat_penalty_scale,
                enemy_pattern_scale=self.enemy_pattern_scale,
                score_open_four=self.pattern_scores["middle"][(4, 2)],
                score_half_four=self.pattern_scores["middle"][(4, 1)],
                score_open_three=self.pattern_scores["middle"][(3, 2)],
                score_half_three=self.pattern_scores["middle"][(3, 1)],
                score_open_two=self.pattern_scores["middle"][(2, 2)],
                score_half_two=self.pattern_scores["middle"][(2, 1)],
                own_win_point_bonus=self.own_win_point_bonus,
                enemy_win_point_penalty=self.enemy_win_point_penalty,
                own_open_four_bonus=self.own_open_four_bonus,
                enemy_open_four_penalty=self.enemy_open_four_penalty,
                enemy_major_threat_penalty=self.enemy_major_threat_penalty,
                use_lazy_smp=False,
            )

        return parallel.best_move(board, stone, ai_builder=builder)

    def _search_root(
        self,
        board: GameBoard,
        ai_stone: int,
        depth: int,
        alpha: int = -10**18,
        beta: int = 10**18,
    ) -> Tuple[Optional[Move], int]:
        best: Optional[Move] = None
        best_score = -10**18
        root_hash = self._board_hash(board)
        root_core_state: Optional[SegmentCoreState] = None
        if self.use_incremental_core_eval and self.use_segment_core_eval:
            root_core_state = self._segment_core_state(board)
            root_core_black, root_core_white = root_core_state.score_black, root_core_state.score_white
        elif self.use_incremental_core_eval:
            root_core_black, root_core_white = self._core_board_scores(board)
        else:
            root_core_black, root_core_white = 0, 0

        moves = self._sorted_moves(board, self._candidate_moves(board, ai_stone), ai_stone, ply=0, board_hash=root_hash)
        for move in moves:
            self._check_timeout()
            if not self._is_legal_move(board, move.x, move.y, ai_stone):
                continue
            placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                board, move.x, move.y, ai_stone, root_core_black, root_core_white, root_core_state
            )
            if not placed:
                continue
            child_hash = self._xor_hash_move(root_hash, move.x, move.y, ai_stone)
            try:
                score = self.WIN_SCORE if board.winner == ai_stone else self._minimax(
                    board=board,
                    depth=depth - 1,
                    maximizing=False,
                    ai_stone=ai_stone,
                    current_stone=opponent(ai_stone),
                    alpha=alpha,
                    beta=beta,
                    ply=1,
                    board_hash=child_hash,
                    core_black=child_core_black,
                    core_white=child_core_white,
                    core_state=child_core_state,
                )
            finally:
                board.remove(move.x, move.y)
            if score > best_score:
                best_score = score
                best = Move(move.x, move.y, score)
            if score > alpha:
                alpha = score
        return best, best_score

    def _minimax(
        self,
        board: GameBoard,
        depth: int,
        maximizing: bool,
        ai_stone: int,
        current_stone: int,
        alpha: int,
        beta: int,
        ply: int,
        board_hash: int,
        core_black: Optional[int] = None,
        core_white: Optional[int] = None,
        core_state: Optional[SegmentCoreState] = None,
    ) -> int:
        self._check_timeout()
        if self.use_incremental_core_eval and self.use_segment_core_eval and core_state is None:
            core_state = self._segment_core_state(board)
            core_black, core_white = core_state.score_black, core_state.score_white
        elif self.use_incremental_core_eval and (core_black is None or core_white is None):
            core_black, core_white = self._core_board_scores(board)
        elif core_black is None or core_white is None:
            core_black, core_white = 0, 0
        cache_key = (board_hash, maximizing, ai_stone, current_stone)
        alpha_orig = alpha
        beta_orig = beta
        cached = self._tt.get(cache_key)
        if cached is not None and cached.depth >= depth:
            if cached.flag == self.TT_EXACT:
                return cached.score
            if cached.flag == self.TT_LOWER:
                alpha = max(alpha, cached.score)
            elif cached.flag == self.TT_UPPER:
                beta = min(beta, cached.score)
            if alpha >= beta:
                return cached.score

        if depth <= 0 or board.is_game_over:
            if board.is_game_over:
                score = self._evaluate_board_current(board, ai_stone, core_black, core_white)
            elif self.use_quiescence:
                score = self._quiescence(
                    board=board,
                    maximizing=maximizing,
                    ai_stone=ai_stone,
                    current_stone=current_stone,
                    alpha=alpha,
                    beta=beta,
                    qply=0,
                    core_black=core_black,
                    core_white=core_white,
                    core_state=core_state,
                )
            else:
                score = self._evaluate_board_current(board, ai_stone, core_black, core_white)
            self._tt[cache_key] = TTEntry(score=score, flag=self.TT_EXACT, depth=depth)
            return score

        forced = self._forced_move(board, current_stone)
        if forced is not None:
            score = self.FORCE_SCORE if current_stone == ai_stone else -self.FORCE_SCORE
            self._tt[cache_key] = TTEntry(score=score, flag=self.TT_EXACT, depth=depth)
            return score

        moves = self._sorted_moves(
            board,
            self._candidate_moves(board, current_stone),
            current_stone,
            ply=ply,
            board_hash=board_hash,
        )
        if self.use_iid and depth >= self.iid_min_depth and len(moves) > 1:
            hint = self._iid_probe_move(
                board, current_stone, ai_stone, depth, ply, board_hash, core_black, core_white, core_state
            )
            if hint is not None:
                moves = self._prioritize_hint(moves, hint)
        if not moves:
            score = self._evaluate_board_current(board, ai_stone, core_black, core_white)
            self._tt[cache_key] = TTEntry(score=score, flag=self.TT_EXACT, depth=depth)
            return score

        if maximizing:
            value = -10**18
            best_cut: Optional[Move] = None
            has_legal = False
            first = True
            for index, move in enumerate(moves):
                if not self._is_legal_move(board, move.x, move.y, current_stone):
                    continue
                has_legal = True
                placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                    board, move.x, move.y, current_stone, core_black, core_white, core_state
                )
                if not placed:
                    continue
                child_hash = self._xor_hash_move(board_hash, move.x, move.y, current_stone)
                next_depth = depth - 1 + self._tactical_extension(board, move.x, move.y, current_stone, depth, ply)
                try:
                    if board.winner == current_stone:
                        score = self.WIN_SCORE - (self._iterative_depth - depth)
                    elif self.use_pvs and not first:
                        reduced = (
                            self.use_lmr
                            and depth >= self.LMR_MIN_DEPTH
                            and index >= self.LMR_MIN_INDEX
                            and next_depth >= 2
                            and not self._is_forcing_move(board, move.x, move.y, current_stone)
                        )
                        lmr_depth = next_depth - 1 if reduced else next_depth
                        score = self._minimax(
                            board,
                            lmr_depth,
                            False,
                            ai_stone,
                            opponent(current_stone),
                            alpha,
                            alpha + 1,
                            ply + 1,
                            child_hash,
                            child_core_black,
                            child_core_white,
                            child_core_state,
                        )
                        if alpha < score < beta or (reduced and score > alpha):
                            score = self._minimax(
                                board,
                                next_depth,
                                False,
                                ai_stone,
                                opponent(current_stone),
                                alpha,
                                beta,
                                ply + 1,
                                child_hash,
                                child_core_black,
                                child_core_white,
                                child_core_state,
                            )
                    else:
                        # LMR: reduce late, quiet moves and re-search only if needed.
                        reduced = (
                            self.use_lmr
                            and depth >= self.LMR_MIN_DEPTH
                            and index >= self.LMR_MIN_INDEX
                            and next_depth >= 2
                            and not self._is_forcing_move(board, move.x, move.y, current_stone)
                        )
                        if reduced:
                            score = self._minimax(
                                board,
                                next_depth - 1,
                                False,
                                ai_stone,
                                opponent(current_stone),
                                alpha,
                                beta,
                                ply + 1,
                                child_hash,
                                child_core_black,
                                child_core_white,
                                child_core_state,
                            )
                            if score > alpha:
                                score = self._minimax(
                                    board,
                                    next_depth,
                                    False,
                                    ai_stone,
                                    opponent(current_stone),
                                    alpha,
                                    beta,
                                    ply + 1,
                                    child_hash,
                                    child_core_black,
                                    child_core_white,
                                    child_core_state,
                                )
                        else:
                            score = self._minimax(
                                board,
                                next_depth,
                                False,
                                ai_stone,
                                opponent(current_stone),
                                alpha,
                                beta,
                                ply + 1,
                                child_hash,
                                child_core_black,
                                child_core_white,
                                child_core_state,
                            )
                finally:
                    board.remove(move.x, move.y)
                if score > value:
                    value = score
                    best_cut = move
                value = max(value, score)
                alpha = max(alpha, value)
                first = False
                if beta <= alpha:
                    self._record_cutoff(ply, move, current_stone, depth)
                    break
            if not has_legal:
                value = self._evaluate_board_current(board, ai_stone, core_black, core_white)
            if best_cut is not None:
                self._history_table[(current_stone, best_cut.x, best_cut.y)] = self._history_table.get(
                    (current_stone, best_cut.x, best_cut.y), 0
                ) + depth * depth
            flag = self.TT_EXACT
            if value <= alpha_orig:
                flag = self.TT_UPPER
            elif value >= beta_orig:
                flag = self.TT_LOWER
            self._tt[cache_key] = TTEntry(score=value, flag=flag, depth=depth)
            return value

        value = 10**18
        best_cut: Optional[Move] = None
        has_legal = False
        first = True
        for index, move in enumerate(moves):
            if not self._is_legal_move(board, move.x, move.y, current_stone):
                continue
            has_legal = True
            placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                board, move.x, move.y, current_stone, core_black, core_white, core_state
            )
            if not placed:
                continue
            child_hash = self._xor_hash_move(board_hash, move.x, move.y, current_stone)
            next_depth = depth - 1 + self._tactical_extension(board, move.x, move.y, current_stone, depth, ply)
            try:
                if board.winner == current_stone:
                    score = -self.WIN_SCORE + (self._iterative_depth - depth)
                elif self.use_pvs and not first:
                    reduced = (
                        self.use_lmr
                        and depth >= self.LMR_MIN_DEPTH
                        and index >= self.LMR_MIN_INDEX
                        and next_depth >= 2
                        and not self._is_forcing_move(board, move.x, move.y, current_stone)
                    )
                    lmr_depth = next_depth - 1 if reduced else next_depth
                    score = self._minimax(
                        board,
                        lmr_depth,
                        True,
                        ai_stone,
                        opponent(current_stone),
                        beta - 1,
                        beta,
                        ply + 1,
                        child_hash,
                        child_core_black,
                        child_core_white,
                        child_core_state,
                    )
                    if alpha < score < beta or (reduced and score < beta):
                        score = self._minimax(
                            board,
                            next_depth,
                            True,
                            ai_stone,
                            opponent(current_stone),
                            alpha,
                            beta,
                            ply + 1,
                            child_hash,
                            child_core_black,
                            child_core_white,
                            child_core_state,
                        )
                else:
                    reduced = (
                        self.use_lmr
                        and depth >= self.LMR_MIN_DEPTH
                        and index >= self.LMR_MIN_INDEX
                        and next_depth >= 2
                        and not self._is_forcing_move(board, move.x, move.y, current_stone)
                    )
                    if reduced:
                        score = self._minimax(
                            board,
                            next_depth - 1,
                            True,
                            ai_stone,
                            opponent(current_stone),
                            alpha,
                            beta,
                            ply + 1,
                            child_hash,
                            child_core_black,
                            child_core_white,
                            child_core_state,
                        )
                        if score < beta:
                            score = self._minimax(
                                board,
                                next_depth,
                                True,
                                ai_stone,
                                opponent(current_stone),
                                alpha,
                                beta,
                                ply + 1,
                                child_hash,
                                child_core_black,
                                child_core_white,
                                child_core_state,
                            )
                    else:
                        score = self._minimax(
                            board,
                            next_depth,
                            True,
                            ai_stone,
                            opponent(current_stone),
                            alpha,
                            beta,
                            ply + 1,
                            child_hash,
                            child_core_black,
                            child_core_white,
                            child_core_state,
                        )
            finally:
                board.remove(move.x, move.y)
            if score < value:
                value = score
                best_cut = move
            value = min(value, score)
            beta = min(beta, value)
            first = False
            if beta <= alpha:
                self._record_cutoff(ply, move, current_stone, depth)
                break
        if not has_legal:
            value = self._evaluate_board_current(board, ai_stone, core_black, core_white)
        if best_cut is not None:
            self._history_table[(current_stone, best_cut.x, best_cut.y)] = self._history_table.get(
                (current_stone, best_cut.x, best_cut.y), 0
            ) + depth * depth
        flag = self.TT_EXACT
        if value <= alpha_orig:
            flag = self.TT_UPPER
        elif value >= beta_orig:
            flag = self.TT_LOWER
        self._tt[cache_key] = TTEntry(score=value, flag=flag, depth=depth)
        return value

    def _sorted_moves(self, board: GameBoard, moves: List[Move], stone: int, ply: int, board_hash: Optional[int] = None) -> List[Move]:
        move_key = tuple(sorted((move.x, move.y) for move in moves))
        if board_hash is None:
            board_hash = self._board_hash(board)
        cache_key = (board_hash, stone, ply, move_key)
        if cache_key in self._move_score_cache:
            return [Move(move.x, move.y, move.score) for move in self._move_score_cache[cache_key]]

        moves = self._prefilter_moves(board, moves, stone)
        ranked = self._rank_moves(board, moves, stone, ply=ply)
        result = [Move(move.x, move.y, move.score) for move in ranked[: self.MOVE_CANDIDATE_LIMIT]]
        self._move_score_cache[cache_key] = result
        return [Move(move.x, move.y, move.score) for move in result]

    def _candidate_moves(self, board: GameBoard, stone: int) -> List[Move]:
        # Hard priority rule: defense points must always outrank heuristic history/killer.
        must_block = self._must_block_moves(board, stone)
        if must_block:
            return must_block[: self.MOVE_CANDIDATE_LIMIT]

        if self.use_threat_space:
            forcing = self._forcing_moves(board, stone)
            if forcing:
                return forcing[: self.MOVE_CANDIDATE_LIMIT]

        moves = board.focused_candidate_moves()
        if len(moves) >= 6:
            return moves
        return board.candidate_moves()

    def _forced_move(self, board: GameBoard, stone: int) -> Optional[Move]:
        win_now = self._find_winning_move(board, stone)
        if win_now is not None:
            win_now.score = self.WIN_SCORE
            return win_now

        enemy = opponent(stone)
        block_enemy = self._find_winning_move(board, enemy)
        if block_enemy is not None:
            block_enemy.score = self.FORCE_SCORE
            return block_enemy

        urgent = self._find_open_four_response(board, stone)
        if urgent is not None:
            urgent.score = self.FORCE_SCORE // 2
            return urgent

        defend = self._find_open_four_response(board, enemy)
        if defend is not None:
            defend.score = self.FORCE_SCORE // 2
            return defend

        return None

    def _urgent_moves(self, board: GameBoard, stone: int) -> List[Move]:
        focused = board.focused_candidate_moves(distance=3, limit_area=6)
        broad = board.candidate_moves()

        seen: set[Tuple[int, int]] = set()
        merged: List[Move] = []
        for move in focused + broad:
            key = (move.x, move.y)
            if key in seen:
                continue
            seen.add(key)
            merged.append(Move(move.x, move.y))
        return self._rank_moves(board, merged, stone, ply=0)

    def _rank_moves(self, board: GameBoard, moves: List[Move], stone: int, ply: int) -> List[Move]:
        ranked = [Move(move.x, move.y, move.score) for move in moves]
        enemy = opponent(stone)
        killers = self._killer_moves.get(ply, [])
        prioritized: List[Tuple[int, int, Move]] = []
        for move in ranked:
            if not self._is_legal_move(board, move.x, move.y, stone):
                move.score = -10**17
                prioritized.append((self.TIER_NORMAL + 1, move.score, move))
                continue
            board.place(move.x, move.y, stone)
            own_win_now = board.winner == stone
            attack = self.evaluate_position(board, move.x, move.y, stone)
            attack += self._fork_bonus(board, stone)
            attack += self._threat_space_bonus(board, move.x, move.y, stone)
            own_four_threat = self._creates_four_threat(board, move.x, move.y, stone)
            own_double_three = _count_open_three_directions(board, move.x, move.y, stone) >= 2
            board.remove(move.x, move.y)

            board.place(move.x, move.y, enemy)
            enemy_win_now = board.winner == enemy
            defend = self.evaluate_position(board, move.x, move.y, enemy)
            defend += self._fork_bonus(board, enemy)
            defend += self._threat_space_bonus(board, move.x, move.y, enemy)
            blocks_enemy_open_four = self._is_open_four_created(board, move.x, move.y, enemy)
            blocks_enemy_combo = self._creates_four_three_combo(board, move.x, move.y, enemy)
            board.remove(move.x, move.y)

            history_score = self._history_table.get((stone, move.x, move.y), 0) // 3
            killer_score = 90_000 if (move.x, move.y) in killers else 0
            defend_weight = 3 if blocks_enemy_combo else 2
            heuristic_score = attack + (defend * defend_weight) // 4 + history_score + killer_score
            move.score = heuristic_score
            tier = self._move_priority_tier(
                own_win_now=own_win_now,
                enemy_win_now=enemy_win_now,
                blocks_enemy_open_four=blocks_enemy_open_four,
                blocks_enemy_combo=blocks_enemy_combo,
                own_four_threat=own_four_threat,
                own_double_three=own_double_three,
            )
            prioritized.append((tier, -heuristic_score, move))

        prioritized.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in prioritized]

    def _move_priority_tier(
        self,
        own_win_now: bool,
        enemy_win_now: bool,
        blocks_enemy_open_four: bool,
        blocks_enemy_combo: bool,
        own_four_threat: bool,
        own_double_three: bool,
    ) -> int:
        if own_win_now:
            return self.TIER_OWN_FIVE
        if enemy_win_now:
            return self.TIER_BLOCK_ENEMY_FIVE
        if blocks_enemy_open_four:
            return self.TIER_BLOCK_ENEMY_OPEN_FOUR
        if blocks_enemy_combo:
            return self.TIER_BLOCK_ENEMY_COMBO
        if own_four_threat:
            return self.TIER_OWN_FOUR_THREAT
        if own_double_three:
            return self.TIER_OWN_DOUBLE_THREE
        return self.TIER_NORMAL

    def _creates_four_threat(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                return True
        return False

    def _creates_four_three_combo(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        four_threats = 0
        open_threes = 0
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                four_threats += 1
            elif count == 3 and open_ends == 2:
                open_threes += 1
        return four_threats >= 2 or (four_threats >= 1 and open_threes >= 1) or open_threes >= 2

    def _find_winning_move(self, board: GameBoard, stone: int) -> Optional[Move]:
        for move in self._urgent_moves(board, stone):
            if not self._is_legal_move(board, move.x, move.y, stone):
                continue
            board.place(move.x, move.y, stone)
            is_win = board.winner == stone
            board.remove(move.x, move.y)
            if is_win:
                return Move(move.x, move.y, self.WIN_SCORE)
        return None

    def _find_open_four_response(self, board: GameBoard, stone: int) -> Optional[Move]:
        for move in self._urgent_moves(board, stone):
            if not self._is_legal_move(board, move.x, move.y, stone):
                continue
            board.place(move.x, move.y, stone)
            creates_threat = self._is_open_four_created(board, move.x, move.y, stone)
            board.remove(move.x, move.y)
            if creates_threat:
                return Move(move.x, move.y, self.FORCE_SCORE // 2)
        return None

    def _fork_bonus(self, board: GameBoard, stone: int) -> int:
        wins = len(board.immediate_winning_points(stone, limit=3))
        if wins >= 2:
            return 250_000
        if wins == 1:
            return 60_000
        return 0

    def _is_legal_move(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        if self._legal_move_checker is None:
            return True
        return self._legal_move_checker(board, x, y, stone)

    def _must_block_moves(self, board: GameBoard, stone: int) -> List[Move]:
        enemy = opponent(stone)
        seen: set[Tuple[int, int]] = set()
        out: List[Move] = []
        for x, y in board.immediate_winning_points(enemy, limit=12):
            if self._is_legal_move(board, x, y, stone) and (x, y) not in seen:
                seen.add((x, y))
                out.append(Move(x, y, self.FORCE_SCORE))
        if out:
            return out
        for move in self._find_open_four_points(board, enemy, limit=10):
            if self._is_legal_move(board, move.x, move.y, stone) and (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                out.append(Move(move.x, move.y, self.FORCE_SCORE // 2))
        if out:
            return out
        for move in self._find_combo_threat_points(board, enemy, defender=stone, limit=10):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                out.append(move)
        return out

    def _find_combo_threat_response(self, board: GameBoard, stone: int) -> Optional[Move]:
        enemy = opponent(stone)
        points = self._find_combo_threat_points(board, enemy, defender=stone, limit=1)
        return points[0] if points else None

    def _find_combo_threat_points(
        self,
        board: GameBoard,
        attacker: int,
        defender: Optional[int] = None,
        limit: int = 8,
    ) -> List[Move]:
        defender_stone = opponent(attacker) if defender is None else defender
        points: List[Move] = []
        seen: set[Tuple[int, int]] = set()
        for move in board.focused_candidate_moves(distance=3, limit_area=6):
            if (move.x, move.y) in seen:
                continue
            if not self._is_legal_move(board, move.x, move.y, defender_stone):
                continue
            if not self._is_legal_move(board, move.x, move.y, attacker):
                continue
            board.place(move.x, move.y, attacker)
            combo = self._creates_four_three_combo(board, move.x, move.y, attacker)
            board.remove(move.x, move.y)
            if combo:
                seen.add((move.x, move.y))
                points.append(Move(move.x, move.y, self.FORCE_SCORE // 3))
                if len(points) >= limit:
                    break
        return points

    def _iid_probe_move(
        self,
        board: GameBoard,
        current_stone: int,
        ai_stone: int,
        depth: int,
        ply: int,
        board_hash: int,
        core_black: int,
        core_white: int,
        core_state: Optional[SegmentCoreState] = None,
    ) -> Optional[Tuple[int, int]]:
        shallow_depth = max(1, depth - 2)
        probe_moves = self._sorted_moves(
            board, board.focused_candidate_moves(), current_stone, ply=ply, board_hash=board_hash
        )
        if not probe_moves:
            return None
        best: Optional[Tuple[int, int]] = None
        best_score = -10**18
        for move in probe_moves[:8]:
            if not self._is_legal_move(board, move.x, move.y, current_stone):
                continue
            placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                board, move.x, move.y, current_stone, core_black, core_white, core_state
            )
            if not placed:
                continue
            child_hash = self._xor_hash_move(board_hash, move.x, move.y, current_stone)
            score = self.WIN_SCORE if board.winner == current_stone else self._minimax(
                board,
                shallow_depth - 1,
                maximizing=(opponent(current_stone) == ai_stone),
                ai_stone=ai_stone,
                current_stone=opponent(current_stone),
                alpha=-10**18,
                beta=10**18,
                ply=ply + 1,
                board_hash=child_hash,
                core_black=child_core_black,
                core_white=child_core_white,
                core_state=child_core_state,
            )
            board.remove(move.x, move.y)
            if score > best_score:
                best_score = score
                best = (move.x, move.y)
        return best

    def _is_forcing_move(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        if board.winner == stone:
            return True
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                return True
            if count == 3 and open_ends == 2:
                return True
        return False

    def _prioritize_hint(self, moves: List[Move], hint: Tuple[int, int]) -> List[Move]:
        if not moves:
            return moves
        hx, hy = hint
        prioritized: List[Move] = []
        rest: List[Move] = []
        for move in moves:
            if move.x == hx and move.y == hy:
                prioritized.append(move)
            else:
                rest.append(move)
        return prioritized + rest

    def _forcing_moves(self, board: GameBoard, stone: int) -> List[Move]:
        if not self.use_threat_space:
            return []
        enemy = opponent(stone)
        forced: List[Move] = []
        seen: set[Tuple[int, int]] = set()

        for move in self._find_winning_points(board, stone, limit=6):
            seen.add((move.x, move.y))
            forced.append(move)
        if forced:
            return forced

        for move in self._find_winning_points(board, enemy, limit=6):
            if (move.x, move.y) not in seen and self._is_legal_move(board, move.x, move.y, stone):
                seen.add((move.x, move.y))
                forced.append(Move(move.x, move.y, self.FORCE_SCORE))
        if forced:
            return forced

        for move in self._find_open_four_points(board, stone, limit=8):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                forced.append(move)
        if forced:
            return forced[:10]

        for move in self._find_open_four_points(board, enemy, limit=8):
            if (move.x, move.y) not in seen and self._is_legal_move(board, move.x, move.y, stone):
                seen.add((move.x, move.y))
                forced.append(Move(move.x, move.y, self.FORCE_SCORE // 2))
        if forced:
            return forced[:10]

        for move in self._find_major_threat_points(board, stone, limit=8):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                forced.append(move)
        for move in self._find_major_threat_points(board, enemy, limit=8):
            if (move.x, move.y) not in seen and self._is_legal_move(board, move.x, move.y, stone):
                seen.add((move.x, move.y))
                forced.append(Move(move.x, move.y, move.score // 2))
        return forced[:10]

    def _find_winning_points(self, board: GameBoard, stone: int, limit: int = 6) -> List[Move]:
        points: List[Move] = []
        for move in board.focused_candidate_moves(distance=3, limit_area=6):
            if not self._is_legal_move(board, move.x, move.y, stone):
                continue
            board.place(move.x, move.y, stone)
            is_win = board.winner == stone
            board.remove(move.x, move.y)
            if is_win:
                points.append(Move(move.x, move.y, self.WIN_SCORE))
                if len(points) >= limit:
                    break
        return points

    def _find_major_threat_points(self, board: GameBoard, stone: int, limit: int = 8) -> List[Move]:
        points: List[Move] = []
        for move in board.focused_candidate_moves(distance=3, limit_area=6):
            if not self._is_legal_move(board, move.x, move.y, stone):
                continue
            board.place(move.x, move.y, stone)
            major = self._creates_major_threat(board, move.x, move.y, stone)
            board.remove(move.x, move.y)
            if major:
                points.append(Move(move.x, move.y, self.FORCE_SCORE // 3))
                if len(points) >= limit:
                    break
        return points

    def _find_open_four_points(self, board: GameBoard, stone: int, limit: int = 8) -> List[Move]:
        points: List[Move] = []
        for move in board.focused_candidate_moves(distance=3, limit_area=6):
            if not self._is_legal_move(board, move.x, move.y, stone):
                continue
            board.place(move.x, move.y, stone)
            is_open_four = self._is_open_four_created(board, move.x, move.y, stone)
            board.remove(move.x, move.y)
            if is_open_four:
                points.append(Move(move.x, move.y, self.FORCE_SCORE // 2))
                if len(points) >= limit:
                    break
        return points

    def _creates_major_threat(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                return True
            if count == 3 and open_ends == 2:
                return True
        return False

    def _is_open_four_created(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count == 4 and open_ends == 2:
                return True
        return False

    def _threat_space_bonus(self, board: GameBoard, x: int, y: int, stone: int) -> int:
        if not self.use_threat_space:
            return 0
        if self.use_pattern_lookup:
            try:
                from engine_p1 import PatternEvaluator, ThreatLevel  # local import

                patterns = PatternEvaluator.classify_directions(board, x, y, stone)
                level = PatternEvaluator.classify_threat(patterns)
                if level == ThreatLevel.WIN:
                    return 260_000
                if level == ThreatLevel.MUST_BLOCK:
                    return 170_000
                if level == ThreatLevel.FORCING:
                    return 80_000
            except Exception:
                pass
        major_dirs = 0
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                major_dirs += 2
            elif count == 3 and open_ends == 2:
                major_dirs += 1
        return major_dirs * 45_000

    def evaluate_board(self, board: GameBoard, ai_stone: int) -> int:
        enemy = opponent(ai_stone)
        phase = self._game_phase(board)
        score = 0
        min_x, max_x, min_y, max_y = board.occupied_bounds(padding=1)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                stone = board.get(x, y)
                if stone == EMPTY:
                    continue
                value = self.evaluate_position(board, x, y, stone, phase)
                score += value if stone == ai_stone else -value
        own_threat = self._threat_score(board, ai_stone, phase)
        enemy_threat = self._threat_score(board, enemy, phase)
        score += own_threat - int(enemy_threat * self.enemy_threat_penalty_scale)
        if self.use_defense_urgency:
            score += self._defense_urgency_adjustment(board, ai_stone)
        if self.use_eval_correction and abs(score) < self.WIN_SCORE // 4:
            score += self._eval_residual(board, ai_stone, base_score=score)
        return score

    def _core_board_scores(self, board: GameBoard) -> Tuple[int, int]:
        if self.use_segment_core_eval:
            return self._segment_board_scores(board)

        phase = self._game_phase(board)
        black_score = 0
        white_score = 0
        min_x, max_x, min_y, max_y = board.occupied_bounds(padding=1)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                stone = board.get(x, y)
                if stone == BLACK:
                    black_score += self.evaluate_position(board, x, y, BLACK, phase)
                elif stone == WHITE:
                    white_score += self.evaluate_position(board, x, y, WHITE, phase)
        return black_score, white_score

    def _segment_board_scores(self, board: GameBoard) -> Tuple[int, int]:
        state = self._segment_core_state(board)
        return state.score_black, state.score_white

    def _segment_core_state(self, board: GameBoard) -> SegmentCoreState:
        phase = self._game_phase(board)
        raw_black = 0
        raw_white = 0
        black_counts = (0, 0, 0, 0)
        white_counts = (0, 0, 0, 0)
        entries: List[SegmentLineEntry] = []

        lines, _point_to_lines = self._segment_geometry(board)
        for coords in lines:
            cells = [board.get(x, y) for x, y in coords]
            line_black, counts_black = self._score_segment_line(cells, BLACK, phase)
            line_white, counts_white = self._score_segment_line(cells, WHITE, phase)
            black_tuple = self._counts_dict_to_tuple(counts_black)
            white_tuple = self._counts_dict_to_tuple(counts_white)
            entries.append(SegmentLineEntry(line_black, line_white, black_tuple, white_tuple))
            raw_black += line_black
            raw_white += line_white
            black_counts = self._add_count_tuples(black_counts, black_tuple)
            white_counts = self._add_count_tuples(white_counts, white_tuple)

        return self._build_segment_state(raw_black, raw_white, black_counts, white_counts, tuple(entries))

    def _segment_geometry(
        self, board: GameBoard
    ) -> Tuple[Tuple[Tuple[Tuple[int, int], ...], ...], Dict[Tuple[int, int], Tuple[int, ...]]]:
        cached = self._SEGMENT_GEOMETRY_CACHE.get(board.size)
        if cached is not None:
            return cached

        size = board.size
        lines: List[Tuple[Tuple[int, int], ...]] = []
        point_to_lines: Dict[Tuple[int, int], List[int]] = {}

        def add_line(coords: List[Tuple[int, int]]) -> None:
            if len(coords) < 5:
                return
            line_id = len(lines)
            line = tuple(coords)
            lines.append(line)
            for point in line:
                point_to_lines.setdefault(point, []).append(line_id)

        for x in range(size):
            add_line([(x, y) for y in range(size)])
        for y in range(size):
            add_line([(x, y) for x in range(size)])

        for start_y in range(size):
            coords = []
            x, y = 0, start_y
            while x < size and y < size:
                coords.append((x, y))
                x += 1
                y += 1
            add_line(coords)
        for start_x in range(1, size):
            coords = []
            x, y = start_x, 0
            while x < size and y < size:
                coords.append((x, y))
                x += 1
                y += 1
            add_line(coords)

        for start_y in range(size):
            coords = []
            x, y = 0, start_y
            while x < size and y >= 0:
                coords.append((x, y))
                x += 1
                y -= 1
            add_line(coords)
        for start_x in range(1, size):
            coords = []
            x, y = start_x, size - 1
            while x < size and y >= 0:
                coords.append((x, y))
                x += 1
                y -= 1
            add_line(coords)

        frozen_map = {point: tuple(ids) for point, ids in point_to_lines.items()}
        cached = (tuple(lines), frozen_map)
        self.__class__._SEGMENT_GEOMETRY_CACHE[size] = cached
        return cached

    def _build_segment_state(
        self,
        raw_black: int,
        raw_white: int,
        black_counts: Tuple[int, int, int, int],
        white_counts: Tuple[int, int, int, int],
        line_entries: Tuple[SegmentLineEntry, ...],
    ) -> SegmentCoreState:
        score_black = raw_black + self._global_segment_threat_bonus_tuple(black_counts)
        score_white = raw_white + self._global_segment_threat_bonus_tuple(white_counts)
        return SegmentCoreState(raw_black, raw_white, score_black, score_white, black_counts, white_counts, line_entries)

    def _counts_dict_to_tuple(self, counts: Dict[str, int]) -> Tuple[int, int, int, int]:
        return (counts["open_three"], counts["four"], counts["open_four"], counts["five"])

    def _add_count_tuples(
        self, left: Tuple[int, int, int, int], right: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        return (left[0] + right[0], left[1] + right[1], left[2] + right[2], left[3] + right[3])

    def _sub_count_tuples(
        self, left: Tuple[int, int, int, int], right: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        return (left[0] - right[0], left[1] - right[1], left[2] - right[2], left[3] - right[3])

    def _score_segment_line(self, cells: Sequence[int], stone: int, phase: str) -> Tuple[int, Dict[str, int]]:
        if len(cells) < 5:
            return 0, {"open_three": 0, "four": 0, "open_four": 0, "five": 0}
        if not self._SEGMENT_WINDOW_TABLES:
            self.__class__._SEGMENT_WINDOW_TABLES = _build_segment_window_tables(self.WIN_SCORE)

        counts = {"open_three": 0, "four": 0, "open_four": 0, "five": 0}
        score = 0
        perspective = [EMPTY if cell == EMPTY else 1 if cell == stone else 2 for cell in cells]
        if len(perspective) < 9:
            left_pad = (9 - len(perspective)) // 2
            right_pad = 9 - len(perspective) - left_pad
            windows = [[2] * left_pad + perspective + [2] * right_pad]
        else:
            windows = [perspective[start : start + 9] for start in range(0, len(perspective) - 8)]

        table = self._SEGMENT_WINDOW_TABLES.get(phase, self._SEGMENT_WINDOW_TABLES["middle"])
        for window in windows:
            code = 0
            for cell in window:
                code = code * 3 + cell
            window_score, open_three, four, open_four, five = table[code]
            score = max(score, window_score)
            counts["open_three"] = max(counts["open_three"], 1 if open_three else 0)
            counts["four"] = max(counts["four"], 1 if four else 0)
            counts["open_four"] = max(counts["open_four"], 1 if open_four else 0)
            counts["five"] = max(counts["five"], 1 if five else 0)
            if five:
                return self.WIN_SCORE, counts
        return score, counts

    def _line_has_five(self, cells: Sequence[int], stone: int) -> bool:
        run = 0
        for cell in cells:
            run = run + 1 if cell == stone else 0
            if run >= 5:
                return True
        return False

    def _line_winning_points(self, cells: Sequence[int], stone: int) -> set[int]:
        points: set[int] = set()
        mutable = list(cells)
        for index, cell in enumerate(cells):
            if cell != EMPTY:
                continue
            mutable[index] = stone
            if self._line_has_five(mutable, stone):
                points.add(index)
            mutable[index] = EMPTY
        return points

    def _line_open_three_moves(self, cells: Sequence[int], stone: int) -> set[int]:
        moves: set[int] = set()
        mutable = list(cells)
        for index, cell in enumerate(cells):
            if cell != EMPTY:
                continue
            mutable[index] = stone
            if len(self._line_winning_points(mutable, stone)) >= 2:
                moves.add(index)
            mutable[index] = EMPTY
        return moves

    def _line_minor_shape_score(self, cells: Sequence[int], stone: int, phase: str) -> int:
        open_two = 0
        blocked_three = 0
        index = 0
        while index < len(cells):
            if cells[index] != stone:
                index += 1
                continue
            start = index
            while index < len(cells) and cells[index] == stone:
                index += 1
            length = index - start
            left_open = start > 0 and cells[start - 1] == EMPTY
            right_open = index < len(cells) and cells[index] == EMPTY
            open_ends = int(left_open) + int(right_open)
            if length == 3 and open_ends == 1:
                blocked_three += 1
            elif length == 2 and open_ends == 2:
                open_two += 1
        if phase == "opening":
            return open_two * 1_200 + blocked_three * 2_800
        if phase == "ending":
            return open_two * 900 + blocked_three * 3_200
        return open_two * 1_000 + blocked_three * 3_000

    def _phase_four_score(self, phase: str) -> int:
        if phase == "opening":
            return 45_000
        if phase == "ending":
            return 75_000
        return 62_000

    def _phase_open_three_score(self, phase: str) -> int:
        if phase == "opening":
            return 22_000
        if phase == "ending":
            return 20_000
        return 28_000

    def _global_segment_threat_bonus(self, counts: Dict[str, int]) -> int:
        if counts["five"]:
            return self.WIN_SCORE
        bonus = 0
        if counts["open_four"] >= 2:
            bonus += self.WIN_SCORE // 2
        elif counts["open_four"] == 1:
            bonus += 240_000
        if counts["four"] >= 2:
            bonus += 260_000
        elif counts["four"] == 1:
            bonus += 55_000
        if counts["open_three"] >= 2:
            bonus += 120_000 + (counts["open_three"] - 2) * 40_000
        elif counts["open_three"] == 1:
            bonus += 28_000
        return bonus

    def _global_segment_threat_bonus_tuple(self, counts: Tuple[int, int, int, int]) -> int:
        open_three, four, open_four, five = counts
        if five:
            return self.WIN_SCORE
        bonus = 0
        if open_four >= 2:
            bonus += self.WIN_SCORE // 2
        elif open_four == 1:
            bonus += 240_000
        if four >= 2:
            bonus += 260_000
        elif four == 1:
            bonus += 55_000
        if open_three >= 2:
            bonus += 120_000 + (open_three - 2) * 40_000
        elif open_three == 1:
            bonus += 28_000
        return bonus

    def _evaluate_board_from_core(
        self,
        board: GameBoard,
        ai_stone: int,
        core_black: int,
        core_white: int,
    ) -> int:
        if ai_stone == BLACK:
            return core_black - int(core_white * self.enemy_pattern_scale)
        return core_white - int(core_black * self.enemy_pattern_scale)

    def _evaluate_board_current(
        self,
        board: GameBoard,
        ai_stone: int,
        core_black: int,
        core_white: int,
    ) -> int:
        if self.use_incremental_core_eval:
            return self._evaluate_board_from_core(board, ai_stone, core_black, core_white)
        return self.evaluate_board(board, ai_stone)

    def _affected_eval_points(self, board: GameBoard, x: int, y: int) -> List[Tuple[int, int]]:
        seen: set[Tuple[int, int]] = set()
        out: List[Tuple[int, int]] = []
        if board.is_inside(x, y) and board.get(x, y) != EMPTY:
            seen.add((x, y))
            out.append((x, y))
        for dx, dy in DIRECTIONS:
            for sign in (-1, 1):
                for step in range(1, 6):
                    nx = x + sign * step * dx
                    ny = y + sign * step * dy
                    if not board.is_inside(nx, ny):
                        break
                    if board.get(nx, ny) != EMPTY and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        out.append((nx, ny))
        return out

    def _core_score_for_points(
        self,
        board: GameBoard,
        points: Sequence[Tuple[int, int]],
        phase: str,
    ) -> Tuple[int, int]:
        black_score = 0
        white_score = 0
        for x, y in points:
            stone = board.get(x, y)
            if stone == BLACK:
                black_score += self.evaluate_position(board, x, y, BLACK, phase)
            elif stone == WHITE:
                white_score += self.evaluate_position(board, x, y, WHITE, phase)
        return black_score, white_score

    def _place_with_core(
        self,
        board: GameBoard,
        x: int,
        y: int,
        stone: int,
        core_black: int,
        core_white: int,
        core_state: Optional[SegmentCoreState] = None,
    ) -> Tuple[bool, int, int, Optional[SegmentCoreState]]:
        if not self.use_incremental_core_eval:
            return board.place(x, y, stone), core_black, core_white, core_state

        if self.use_segment_core_eval:
            phase_before = self._game_phase(board)
            if not board.place(x, y, stone):
                return False, core_black, core_white, core_state
            if self._game_phase(board) != phase_before:
                next_state = self._segment_core_state(board)
                return True, next_state.score_black, next_state.score_white, next_state
            if core_state is None:
                core_state = self._segment_core_state(board)
                return True, core_state.score_black, core_state.score_white, core_state
            next_state = self._update_segment_core_state(board, x, y, core_state)
            return True, next_state.score_black, next_state.score_white, next_state

        phase_before = self._game_phase(board)
        affected_before = self._affected_eval_points(board, x, y)
        old_black, old_white = self._core_score_for_points(board, affected_before, phase_before)
        if not board.place(x, y, stone):
            return False, core_black, core_white, core_state

        phase_after = self._game_phase(board)
        if phase_after != phase_before:
            next_black, next_white = self._core_board_scores(board)
            return True, next_black, next_white, core_state

        affected_after = self._affected_eval_points(board, x, y)
        new_black, new_white = self._core_score_for_points(board, affected_after, phase_after)
        return True, core_black - old_black + new_black, core_white - old_white + new_white, core_state

    def _update_segment_core_state(
        self,
        board: GameBoard,
        x: int,
        y: int,
        state: SegmentCoreState,
    ) -> SegmentCoreState:
        phase = self._game_phase(board)
        lines, point_to_lines = self._segment_geometry(board)
        affected = point_to_lines.get((x, y), ())
        if not affected:
            return state

        entries = list(state.line_entries)
        raw_black = state.raw_black
        raw_white = state.raw_white
        black_counts = state.black_counts
        white_counts = state.white_counts

        for line_id in affected:
            old = entries[line_id]
            raw_black -= old.black_score
            raw_white -= old.white_score
            black_counts = self._sub_count_tuples(black_counts, old.black_counts)
            white_counts = self._sub_count_tuples(white_counts, old.white_counts)

            cells = [board.get(px, py) for px, py in lines[line_id]]
            line_black, counts_black = self._score_segment_line(cells, BLACK, phase)
            line_white, counts_white = self._score_segment_line(cells, WHITE, phase)
            black_tuple = self._counts_dict_to_tuple(counts_black)
            white_tuple = self._counts_dict_to_tuple(counts_white)
            entries[line_id] = SegmentLineEntry(line_black, line_white, black_tuple, white_tuple)
            raw_black += line_black
            raw_white += line_white
            black_counts = self._add_count_tuples(black_counts, black_tuple)
            white_counts = self._add_count_tuples(white_counts, white_tuple)

        return self._build_segment_state(raw_black, raw_white, black_counts, white_counts, tuple(entries))

    def _defense_urgency_adjustment(self, board: GameBoard, ai_stone: int) -> int:
        enemy = opponent(ai_stone)
        own_win_points = len(board.immediate_winning_points(ai_stone, limit=3))
        enemy_win_points = len(board.immediate_winning_points(enemy, limit=3))
        own_open_four = len(self._find_open_four_points(board, ai_stone, limit=3))
        enemy_open_four = len(self._find_open_four_points(board, enemy, limit=3))
        own_major = len(self._find_major_threat_points(board, ai_stone, limit=4))
        enemy_major = len(self._find_major_threat_points(board, enemy, limit=4))

        swing = 0
        swing += own_win_points * self.own_win_point_bonus
        swing -= enemy_win_points * self.enemy_win_point_penalty
        swing += own_open_four * self.own_open_four_bonus
        swing -= enemy_open_four * self.enemy_open_four_penalty
        swing += (own_major - enemy_major) * self.enemy_major_threat_penalty

        # If opponent has direct win points and we don't, force a clear defensive bias.
        if enemy_win_points > 0 and own_win_points == 0:
            swing -= 220_000
        return swing

    def _eval_residual(self, board: GameBoard, ai_stone: int, base_score: int) -> int:
        enemy = opponent(ai_stone)
        ai_wins = len(board.immediate_winning_points(ai_stone, limit=3))
        enemy_wins = len(board.immediate_winning_points(enemy, limit=3))
        ai_open4 = len(self._find_open_four_points(board, ai_stone, limit=4))
        enemy_open4 = len(self._find_open_four_points(board, enemy, limit=4))
        ai_major = len(self._find_major_threat_points(board, ai_stone, limit=4))
        enemy_major = len(self._find_major_threat_points(board, enemy, limit=4))
        feature_score = (
            (ai_wins - enemy_wins) * 260_000
            + (ai_open4 - enemy_open4) * 120_000
            + (ai_major - enemy_major) * 40_000
        )
        limit = int(max(1, abs(base_score) * self.eval_correction_limit))
        if feature_score > limit:
            return limit
        if feature_score < -limit:
            return -limit
        return feature_score

    def _threat_score(self, board: GameBoard, stone: int, phase: str) -> int:
        threat = 0
        for move in board.focused_candidate_moves(distance=2, limit_area=3)[:10]:
            board.place(move.x, move.y, stone)
            threat += self.evaluate_position(board, move.x, move.y, stone, phase) // 8
            board.remove(move.x, move.y)
        return threat

    def _prefilter_moves(self, board: GameBoard, moves: List[Move], stone: int) -> List[Move]:
        if len(moves) <= 14:
            return moves

        enemy = opponent(stone)
        center = board.size // 2
        prescored: List[Move] = []
        for move in moves:
            center_bias = board.size - (abs(move.x - center) + abs(move.y - center))
            adjacency = self._local_density(board, move.x, move.y, stone)
            blocking = self._local_density(board, move.x, move.y, enemy)
            prescored.append(Move(move.x, move.y, center_bias + adjacency * 18 + blocking * 15))
        prescored.sort(key=lambda item: item.score, reverse=True)
        return prescored[:14]

    def _local_density(self, board: GameBoard, x: int, y: int, stone: int) -> int:
        score = 0
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not board.is_inside(nx, ny):
                    continue
                if board.get(nx, ny) == stone:
                    score += 3 if abs(dx) <= 1 and abs(dy) <= 1 else 1
        return score

    def evaluate_position(self, board: GameBoard, x: int, y: int, stone: int, phase: Optional[str] = None) -> int:
        if phase is None:
            phase = self._game_phase(board)
        center = board.size // 2
        total = (board.size - (abs(x - center) + abs(y - center))) * 2
        if self.use_line_pattern_lookup:
            for dx, dy in DIRECTIONS:
                total += self._lookup_line_pattern_score(board, x, y, dx, dy, stone, phase)
            return total
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            total += self._pattern_score(count, open_ends, phase)
        return total

    def _lookup_line_pattern_score(
        self,
        board: GameBoard,
        x: int,
        y: int,
        dx: int,
        dy: int,
        stone: int,
        phase: str,
    ) -> int:
        if not self._LINE_PATTERN_TABLES:
            self.__class__._LINE_PATTERN_TABLES = _build_line_pattern_tables(self.WIN_SCORE)
        code = 0
        for offset in range(-4, 5):
            nx = x + offset * dx
            ny = y + offset * dy
            code *= 3
            if not board.is_inside(nx, ny):
                code += 2
                continue
            cell = board.get(nx, ny)
            if cell == EMPTY:
                continue
            code += 1 if cell == stone else 2
        return self._LINE_PATTERN_TABLES.get(phase, self._LINE_PATTERN_TABLES["middle"])[code]

    def _analyze_line(self, board: GameBoard, x: int, y: int, dx: int, dy: int, stone: int) -> Tuple[int, int]:
        open_ends = 0
        count = 1
        extra, open_ends = self._count(board, x, y, dx, dy, stone, open_ends)
        count += extra
        extra, open_ends = self._count(board, x, y, -dx, -dy, stone, open_ends)
        count += extra
        return count, open_ends

    def _count(self, board: GameBoard, x: int, y: int, dx: int, dy: int, stone: int, open_ends: int) -> Tuple[int, int]:
        count = 0
        cx, cy = x + dx, y + dy
        while board.is_inside(cx, cy) and board.get(cx, cy) == stone:
            count += 1
            cx += dx
            cy += dy
        if board.is_inside(cx, cy) and board.get(cx, cy) == EMPTY:
            open_ends += 1
        return count, open_ends

    def _pattern_score(self, count: int, open_ends: int, phase: str) -> int:
        table = self.pattern_scores.get(phase, self.pattern_scores["middle"])
        if count >= 5:
            return self.WIN_SCORE
        if (count, open_ends) in table:
            return table[(count, open_ends)]
        return 10

    def _game_phase(self, board: GameBoard) -> str:
        ratio = board.move_count / float(board.size * board.size)
        if ratio < 0.12:
            return "opening"
        if ratio > 0.45:
            return "ending"
        return "middle"

    def _record_cutoff(self, ply: int, move: Move, stone: int, depth: int) -> None:
        killers = self._killer_moves.setdefault(ply, [])
        key = (move.x, move.y)
        if key in killers:
            killers.remove(key)
        killers.insert(0, key)
        if len(killers) > 2:
            killers.pop()
        history_key = (stone, move.x, move.y)
        self._history_table[history_key] = self._history_table.get(history_key, 0) + depth * depth * 2

    def _ensure_zobrist(self, size: int) -> None:
        if self._zobrist_size == size and self._zobrist_table:
            return
        rng = random.Random(0x5A17)
        self._zobrist_size = size
        self._zobrist_table = []
        for _x in range(size):
            col: List[Tuple[int, int]] = []
            for _y in range(size):
                col.append((rng.getrandbits(64), rng.getrandbits(64)))
            self._zobrist_table.append(col)

    def _board_hash(self, board: GameBoard) -> int:
        self._ensure_zobrist(board.size)
        h = 0
        for x in range(board.size):
            for y in range(board.size):
                stone = board.get(x, y)
                if stone == EMPTY:
                    continue
                h ^= self._zobrist_table[x][y][0 if stone == BLACK else 1]
        return h

    def _xor_hash_move(self, current_hash: int, x: int, y: int, stone: int) -> int:
        idx = 0 if stone == BLACK else 1
        return current_hash ^ self._zobrist_table[x][y][idx]

    def _time_up(self) -> bool:
        return self._deadline > 0 and time.perf_counter() >= self._deadline

    def _check_timeout(self) -> None:
        if self._time_up():
            raise TimeoutError

    def _tactical_extension(self, board: GameBoard, x: int, y: int, stone: int, depth: int, ply: int) -> int:
        if depth > 2 or ply > 7:
            return 0
        if board.winner == stone:
            return 1
        if self._is_open_four_created(board, x, y, stone):
            return 1
        if self._creates_major_threat(board, x, y, stone):
            return 1
        return 0

    def _quiescence(
        self,
        board: GameBoard,
        maximizing: bool,
        ai_stone: int,
        current_stone: int,
        alpha: int,
        beta: int,
        qply: int,
        core_black: Optional[int] = None,
        core_white: Optional[int] = None,
        core_state: Optional[SegmentCoreState] = None,
    ) -> int:
        self._check_timeout()
        if self.use_incremental_core_eval and self.use_segment_core_eval and core_state is None:
            core_state = self._segment_core_state(board)
            core_black, core_white = core_state.score_black, core_state.score_white
        elif self.use_incremental_core_eval and (core_black is None or core_white is None):
            core_black, core_white = self._core_board_scores(board)
        elif core_black is None or core_white is None:
            core_black, core_white = 0, 0
        stand_pat = self._evaluate_board_current(board, ai_stone, core_black, core_white)
        if qply >= self.QUIESCENCE_MAX_PLY:
            return stand_pat

        if maximizing:
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
        else:
            if stand_pat <= alpha:
                return stand_pat
            beta = min(beta, stand_pat)

        tactical = self._threat_qsearch_moves(board, current_stone) if self.use_threat_qsearch else self._forcing_moves(
            board, current_stone
        )[:8]
        if not tactical:
            return stand_pat

        if maximizing:
            value = stand_pat
            for move in tactical:
                if not self._is_legal_move(board, move.x, move.y, current_stone):
                    continue
                placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                    board, move.x, move.y, current_stone, core_black, core_white, core_state
                )
                if not placed:
                    continue
                score = self.WIN_SCORE - qply if board.winner == current_stone else self._quiescence(
                    board=board,
                    maximizing=False,
                    ai_stone=ai_stone,
                    current_stone=opponent(current_stone),
                    alpha=alpha,
                    beta=beta,
                    qply=qply + 1,
                    core_black=child_core_black,
                    core_white=child_core_white,
                    core_state=child_core_state,
                )
                board.remove(move.x, move.y)
                value = max(value, score)
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value

        value = stand_pat
        for move in tactical:
            if not self._is_legal_move(board, move.x, move.y, current_stone):
                continue
            placed, child_core_black, child_core_white, child_core_state = self._place_with_core(
                board, move.x, move.y, current_stone, core_black, core_white, core_state
            )
            if not placed:
                continue
            score = -self.WIN_SCORE + qply if board.winner == current_stone else self._quiescence(
                board=board,
                maximizing=True,
                ai_stone=ai_stone,
                current_stone=opponent(current_stone),
                alpha=alpha,
                beta=beta,
                qply=qply + 1,
                core_black=child_core_black,
                core_white=child_core_white,
                core_state=child_core_state,
            )
            board.remove(move.x, move.y)
            value = min(value, score)
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    def _threat_qsearch_moves(self, board: GameBoard, stone: int) -> List[Move]:
        seen: set[Tuple[int, int]] = set()
        out: List[Move] = []
        for move in self._find_winning_points(board, stone, limit=4):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                out.append(move)
        for move in self._find_open_four_points(board, stone, limit=4):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                out.append(move)
        for move in self._find_major_threat_points(board, stone, limit=4):
            if (move.x, move.y) not in seen:
                seen.add((move.x, move.y))
                out.append(move)
        enemy = opponent(stone)
        for x, y in board.immediate_winning_points(enemy, limit=4):
            if (x, y) not in seen and self._is_legal_move(board, x, y, stone):
                seen.add((x, y))
                out.append(Move(x, y, self.FORCE_SCORE))
        return out[:8]

    def _explain_move(self, board: GameBoard, stone: int, move: Move) -> str:
        enemy = opponent(stone)

        board.place(move.x, move.y, stone)
        wins_now = board.winner == stone
        board.remove(move.x, move.y)
        if wins_now:
            return "这一手会立刻连成五子，可以当场取胜。"

        board.place(move.x, move.y, enemy)
        blocks_loss = board.winner == enemy
        board.remove(move.x, move.y)
        if blocks_loss:
            return "这一手挡住了对手的直接制胜点，必须先防守。"

        board.place(move.x, move.y, stone)
        longest_line = 1
        best_open_ends = 0
        creates_major_threat = self._creates_major_threat(board, move.x, move.y, stone)
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, move.x, move.y, dx, dy, stone)
            if count > longest_line or (count == longest_line and open_ends > best_open_ends):
                longest_line = count
                best_open_ends = open_ends
        board.remove(move.x, move.y)

        if creates_major_threat:
            return "这一手会形成强制进攻，通常是活三或活四，对手必须应对。"
        if longest_line >= 4:
            return "这一手把你的主攻线扩展到四子，下一步会形成很强的胜势。"
        if longest_line == 3 and best_open_ends >= 1:
            return "这一手把主攻方向推进到三子，并且后续还有继续延展的空间。"
        return "这一手能提升棋盘控制力，呼应附近棋子，并保留更强的后续变化。"
