using System;
using System.Collections.Generic;

namespace Wuziqi
{
    public sealed class AiEngine
    {
        private const int WinScore = 10000000;
        private readonly int _searchDepth;

        public AiEngine(int searchDepth = 2)
        {
            _searchDepth = Math.Max(1, searchDepth);
        }

        public Move FindBestMove(GameBoard board, Stone aiStone)
        {
            var candidates = SortMoves(board, board.GetCandidateMoves(), aiStone);
            Move bestMove = null;
            var bestScore = int.MinValue;
            var opponent = OpponentOf(aiStone);

            foreach (var move in candidates)
            {
                board.PlaceStone(move.X, move.Y, aiStone);
                var score = board.Winner == aiStone
                    ? WinScore
                    : Minimax(board, _searchDepth - 1, false, aiStone, opponent, int.MinValue, int.MaxValue);
                board.RemoveStone(move.X, move.Y);

                if (score > bestScore)
                {
                    bestScore = score;
                    bestMove = new Move(move.X, move.Y, score);
                }
            }

            return bestMove ?? new Move(board.Size / 2, board.Size / 2);
        }

        private int Minimax(GameBoard board, int depth, bool maximizing, Stone aiStone, Stone currentStone, int alpha, int beta)
        {
            if (depth <= 0 || board.IsGameOver)
            {
                return EvaluateBoard(board, aiStone);
            }

            var candidates = SortMoves(board, board.GetCandidateMoves(), currentStone);
            if (candidates.Count == 0)
            {
                return EvaluateBoard(board, aiStone);
            }

            if (maximizing)
            {
                var value = int.MinValue;
                foreach (var move in candidates)
                {
                    board.PlaceStone(move.X, move.Y, currentStone);
                    var score = board.Winner == currentStone
                        ? WinScore - (_searchDepth - depth)
                        : Minimax(board, depth - 1, false, aiStone, OpponentOf(currentStone), alpha, beta);
                    board.RemoveStone(move.X, move.Y);

                    value = Math.Max(value, score);
                    alpha = Math.Max(alpha, value);
                    if (beta <= alpha)
                    {
                        break;
                    }
                }

                return value;
            }

            var minValue = int.MaxValue;
            foreach (var move in candidates)
            {
                board.PlaceStone(move.X, move.Y, currentStone);
                var score = board.Winner == currentStone
                    ? -WinScore + (_searchDepth - depth)
                    : Minimax(board, depth - 1, true, aiStone, OpponentOf(currentStone), alpha, beta);
                board.RemoveStone(move.X, move.Y);

                minValue = Math.Min(minValue, score);
                beta = Math.Min(beta, minValue);
                if (beta <= alpha)
                {
                    break;
                }
            }

            return minValue;
        }

        private List<Move> SortMoves(GameBoard board, List<Move> moves, Stone stone)
        {
            var opponent = OpponentOf(stone);
            foreach (var move in moves)
            {
                board.PlaceStone(move.X, move.Y, stone);
                var attackScore = EvaluatePosition(board, move.X, move.Y, stone);
                board.RemoveStone(move.X, move.Y);

                board.PlaceStone(move.X, move.Y, opponent);
                var defendScore = EvaluatePosition(board, move.X, move.Y, opponent);
                board.RemoveStone(move.X, move.Y);

                move.Score = attackScore + defendScore / 2;
            }

            moves.Sort((a, b) => b.Score.CompareTo(a.Score));
            if (moves.Count > 10)
            {
                moves.RemoveRange(10, moves.Count - 10);
            }

            return moves;
        }

        public int EvaluateBoard(GameBoard board, Stone aiStone)
        {
            var opponent = OpponentOf(aiStone);
            var score = 0;

            for (var x = 0; x < board.Size; x++)
            {
                for (var y = 0; y < board.Size; y++)
                {
                    var stone = board[x, y];
                    if (stone == Stone.Empty)
                    {
                        continue;
                    }

                    var value = EvaluatePosition(board, x, y, stone);
                    score += stone == aiStone ? value : -value;
                }
            }

            score += EvaluateThreats(board, aiStone) - EvaluateThreats(board, opponent);
            return score;
        }

        private int EvaluateThreats(GameBoard board, Stone stone)
        {
            var threatScore = 0;
            foreach (var move in board.GetCandidateMoves())
            {
                board.PlaceStone(move.X, move.Y, stone);
                threatScore += EvaluatePosition(board, move.X, move.Y, stone) / 8;
                board.RemoveStone(move.X, move.Y);
            }

            return threatScore;
        }

        private int EvaluatePosition(GameBoard board, int x, int y, Stone stone)
        {
            var total = 0;
            var center = board.Size / 2;
            total += (board.Size - (Math.Abs(x - center) + Math.Abs(y - center))) * 2;

            var directions = new (int dx, int dy)[]
            {
                (1, 0), (0, 1), (1, 1), (1, -1)
            };

            foreach (var direction in directions)
            {
                var line = AnalyzeLine(board, x, y, direction.dx, direction.dy, stone);
                total += PatternScore(line.count, line.openEnds);
            }

            return total;
        }

        private (int count, int openEnds) AnalyzeLine(GameBoard board, int x, int y, int dx, int dy, Stone stone)
        {
            var count = 1;
            var openEnds = 0;

            count += Count(board, x, y, dx, dy, stone, ref openEnds);
            count += Count(board, x, y, -dx, -dy, stone, ref openEnds);

            return (count, openEnds);
        }

        private int Count(GameBoard board, int x, int y, int dx, int dy, Stone stone, ref int openEnds)
        {
            var count = 0;
            var cx = x + dx;
            var cy = y + dy;

            while (board.IsInside(cx, cy) && board[cx, cy] == stone)
            {
                count++;
                cx += dx;
                cy += dy;
            }

            if (board.IsInside(cx, cy) && board[cx, cy] == Stone.Empty)
            {
                openEnds++;
            }

            return count;
        }

        private int PatternScore(int count, int openEnds)
        {
            if (count >= 5)
            {
                return WinScore;
            }

            if (count == 4 && openEnds == 2)
            {
                return 200000;
            }

            if (count == 4 && openEnds == 1)
            {
                return 50000;
            }

            if (count == 3 && openEnds == 2)
            {
                return 20000;
            }

            if (count == 3 && openEnds == 1)
            {
                return 5000;
            }

            if (count == 2 && openEnds == 2)
            {
                return 1200;
            }

            if (count == 2 && openEnds == 1)
            {
                return 300;
            }

            if (count == 1 && openEnds == 2)
            {
                return 80;
            }

            return 10;
        }

        private Stone OpponentOf(Stone stone)
        {
            return stone == Stone.Black ? Stone.White : Stone.Black;
        }
    }
}
