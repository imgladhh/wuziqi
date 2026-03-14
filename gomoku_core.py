from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


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
        for x in range(self.size):
            for y in range(self.size):
                if self.cells[x][y] == EMPTY and self.has_neighbor(x, y):
                    moves.append(Move(x, y))
        return moves


def opponent(stone: int) -> int:
    return WHITE if stone == BLACK else BLACK


class GomokuAI:
    WIN_SCORE = 10_000_000

    def __init__(self, depth: int = 2) -> None:
        self.depth = max(1, depth)

    def best_move(self, board: GameBoard, ai_stone: int) -> Move:
        best: Optional[Move] = None
        best_score = -10**18
        for move in self._sorted_moves(board, board.candidate_moves(), ai_stone):
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
        return best or Move(board.size // 2, board.size // 2)

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
        if depth <= 0 or board.is_game_over:
            return self.evaluate_board(board, ai_stone)

        moves = self._sorted_moves(board, board.candidate_moves(), current_stone)
        if not moves:
            return self.evaluate_board(board, ai_stone)

        if maximizing:
            value = -10**18
            for move in moves:
                board.place(move.x, move.y, current_stone)
                score = self.WIN_SCORE - (self.depth - depth) if board.winner == current_stone else self._minimax(
                    board, depth - 1, False, ai_stone, opponent(current_stone), alpha, beta
                )
                board.remove(move.x, move.y)
                value = max(value, score)
                alpha = max(alpha, value)
                if beta <= alpha:
                    break
            return value

        value = 10**18
        for move in moves:
            board.place(move.x, move.y, current_stone)
            score = -self.WIN_SCORE + (self.depth - depth) if board.winner == current_stone else self._minimax(
                board, depth - 1, True, ai_stone, opponent(current_stone), alpha, beta
            )
            board.remove(move.x, move.y)
            value = min(value, score)
            beta = min(beta, value)
            if beta <= alpha:
                break
        return value

    def _sorted_moves(self, board: GameBoard, moves: List[Move], stone: int) -> List[Move]:
        enemy = opponent(stone)
        for move in moves:
            board.place(move.x, move.y, stone)
            attack = self.evaluate_position(board, move.x, move.y, stone)
            board.remove(move.x, move.y)

            board.place(move.x, move.y, enemy)
            defend = self.evaluate_position(board, move.x, move.y, enemy)
            board.remove(move.x, move.y)

            move.score = attack + defend // 2
        moves.sort(key=lambda item: item.score, reverse=True)
        return moves[:10]

    def evaluate_board(self, board: GameBoard, ai_stone: int) -> int:
        enemy = opponent(ai_stone)
        score = 0
        for x in range(board.size):
            for y in range(board.size):
                stone = board.get(x, y)
                if stone == EMPTY:
                    continue
                value = self.evaluate_position(board, x, y, stone)
                score += value if stone == ai_stone else -value
        score += self._threat_score(board, ai_stone) - self._threat_score(board, enemy)
        return score

    def _threat_score(self, board: GameBoard, stone: int) -> int:
        threat = 0
        for move in board.candidate_moves():
            board.place(move.x, move.y, stone)
            threat += self.evaluate_position(board, move.x, move.y, stone) // 8
            board.remove(move.x, move.y)
        return threat

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
