from __future__ import annotations

from dataclasses import dataclass
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
    WIN_SCORE = 10_000_000
    FORCE_SCORE = WIN_SCORE // 2

    def __init__(
        self,
        depth: int = 2,
        legal_move_checker: Optional[Callable[[GameBoard, int, int, int], bool]] = None,
    ) -> None:
        self.depth = max(1, depth)
        self._cache: Dict[Tuple[Tuple[Tuple[int, ...], ...], int, bool, int, int], int] = {}
        self._move_score_cache: Dict[Tuple[Tuple[Tuple[int, ...], ...], int, Tuple[Tuple[int, int], ...]], List[Move]] = {}
        self._legal_move_checker = legal_move_checker

    def best_move(self, board: GameBoard, ai_stone: int) -> Move:
        self._cache.clear()
        self._move_score_cache.clear()
        forced = self._forced_move(board, ai_stone)
        if forced is not None:
            return forced

        best: Optional[Move] = None
        best_score = -10**18
        for move in self._sorted_moves(board, self._candidate_moves(board, ai_stone), ai_stone):
            if not self._is_legal_move(board, move.x, move.y, ai_stone):
                continue
            board.place(move.x, move.y, ai_stone)
            score = self.WIN_SCORE if board.winner == ai_stone else self._minimax(
                board,
                self.depth - 1,
                maximizing=False,
                ai_stone=ai_stone,
                current_stone=opponent(ai_stone),
                alpha=-10**18,
                beta=10**18,
            )
            board.remove(move.x, move.y)
            if score > best_score:
                best_score = score
                best = Move(move.x, move.y, score)
        if best is not None:
            return best
        for move in board.candidate_moves():
            if self._is_legal_move(board, move.x, move.y, ai_stone):
                return Move(move.x, move.y)
        return Move(board.size // 2, board.size // 2)

    def suggest_move(self, board: GameBoard, ai_stone: int) -> Tuple[Move, str]:
        move = self.best_move(board, ai_stone)
        reason = self._explain_move(board, ai_stone, move)
        return move, reason

    def _minimax(
        self,
        board: GameBoard,
        depth: int,
        maximizing: bool,
        ai_stone: int,
        current_stone: int,
        alpha: int,
        beta: int,
    ) -> int:
        cache_key = (board.state_key(), depth, maximizing, ai_stone, current_stone)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if depth <= 0 or board.is_game_over:
            score = self.evaluate_board(board, ai_stone)
            self._cache[cache_key] = score
            return score

        forced = self._forced_move(board, current_stone)
        if forced is not None:
            score = self.FORCE_SCORE if current_stone == ai_stone else -self.FORCE_SCORE
            self._cache[cache_key] = score
            return score

        moves = self._sorted_moves(board, self._candidate_moves(board, current_stone), current_stone)
        if not moves:
            score = self.evaluate_board(board, ai_stone)
            self._cache[cache_key] = score
            return score

        if maximizing:
            value = -10**18
            for move in moves:
                if not self._is_legal_move(board, move.x, move.y, current_stone):
                    continue
                board.place(move.x, move.y, current_stone)
                score = self.WIN_SCORE - (self.depth - depth) if board.winner == current_stone else self._minimax(
                    board, depth - 1, False, ai_stone, opponent(current_stone), alpha, beta
                )
                board.remove(move.x, move.y)
                value = max(value, score)
                alpha = max(alpha, value)
                if beta <= alpha:
                    break
            self._cache[cache_key] = value
            return value

        value = 10**18
        for move in moves:
            if not self._is_legal_move(board, move.x, move.y, current_stone):
                continue
            board.place(move.x, move.y, current_stone)
            score = -self.WIN_SCORE + (self.depth - depth) if board.winner == current_stone else self._minimax(
                board, depth - 1, True, ai_stone, opponent(current_stone), alpha, beta
            )
            board.remove(move.x, move.y)
            value = min(value, score)
            beta = min(beta, value)
            if beta <= alpha:
                break
        self._cache[cache_key] = value
        return value

    def _sorted_moves(self, board: GameBoard, moves: List[Move], stone: int) -> List[Move]:
        move_key = tuple(sorted((move.x, move.y) for move in moves))
        cache_key = (board.state_key(), stone, move_key)
        if cache_key in self._move_score_cache:
            return [Move(move.x, move.y, move.score) for move in self._move_score_cache[cache_key]]

        moves = self._prefilter_moves(board, moves, stone)
        ranked = self._rank_moves(board, moves, stone)
        result = [Move(move.x, move.y, move.score) for move in ranked[:12]]
        self._move_score_cache[cache_key] = result
        return [Move(move.x, move.y, move.score) for move in result]

    def _candidate_moves(self, board: GameBoard, stone: int) -> List[Move]:
        moves = board.focused_candidate_moves()
        sorted_moves = self._sorted_moves(board, moves, stone)
        if len(sorted_moves) >= 6:
            return sorted_moves
        return self._sorted_moves(board, board.candidate_moves(), stone)

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
        return self._rank_moves(board, merged, stone)

    def _rank_moves(self, board: GameBoard, moves: List[Move], stone: int) -> List[Move]:
        ranked = [Move(move.x, move.y, move.score) for move in moves]
        enemy = opponent(stone)
        for move in ranked:
            if not self._is_legal_move(board, move.x, move.y, stone):
                move.score = -10**17
                continue
            board.place(move.x, move.y, stone)
            attack = self.evaluate_position(board, move.x, move.y, stone)
            attack += self._fork_bonus(board, stone)
            board.remove(move.x, move.y)

            board.place(move.x, move.y, enemy)
            defend = self.evaluate_position(board, move.x, move.y, enemy)
            defend += self._fork_bonus(board, enemy)
            board.remove(move.x, move.y)

            move.score = attack + defend // 2
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked

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
            creates_threat = self._creates_major_threat(board, move.x, move.y, stone)
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

    def _creates_major_threat(self, board: GameBoard, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            if count >= 4 and open_ends >= 1:
                return True
            if count == 3 and open_ends == 2:
                return True
        return False

    def evaluate_board(self, board: GameBoard, ai_stone: int) -> int:
        enemy = opponent(ai_stone)
        score = 0
        min_x, max_x, min_y, max_y = board.occupied_bounds(padding=1)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                stone = board.get(x, y)
                if stone == EMPTY:
                    continue
                value = self.evaluate_position(board, x, y, stone)
                score += value if stone == ai_stone else -value
        score += self._threat_score(board, ai_stone) - self._threat_score(board, enemy)
        return score

    def _threat_score(self, board: GameBoard, stone: int) -> int:
        threat = 0
        for move in board.focused_candidate_moves(distance=2, limit_area=3)[:10]:
            board.place(move.x, move.y, stone)
            threat += self.evaluate_position(board, move.x, move.y, stone) // 8
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

    def evaluate_position(self, board: GameBoard, x: int, y: int, stone: int) -> int:
        center = board.size // 2
        total = (board.size - (abs(x - center) + abs(y - center))) * 2
        for dx, dy in DIRECTIONS:
            count, open_ends = self._analyze_line(board, x, y, dx, dy, stone)
            total += self._pattern_score(count, open_ends)
        return total

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

    def _pattern_score(self, count: int, open_ends: int) -> int:
        if count >= 5:
            return self.WIN_SCORE
        if count == 4 and open_ends == 2:
            return 200_000
        if count == 4 and open_ends == 1:
            return 50_000
        if count == 3 and open_ends == 2:
            return 20_000
        if count == 3 and open_ends == 1:
            return 5_000
        if count == 2 and open_ends == 2:
            return 1_200
        if count == 2 and open_ends == 1:
            return 300
        if count == 1 and open_ends == 2:
            return 80
        return 10

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
