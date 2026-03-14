using System;
using System.Collections.Generic;

namespace Wuziqi
{
    public enum Stone
    {
        Empty = 0,
        Black = 1,
        White = 2
    }

    public sealed class Move
    {
        public Move(int x, int y, int score = 0)
        {
            X = x;
            Y = y;
            Score = score;
        }

        public int X { get; }
        public int Y { get; }
        public int Score { get; set; }
    }

    public sealed class GameBoard
    {
        private static readonly (int dx, int dy)[] Directions =
        {
            (1, 0), (0, 1), (1, 1), (1, -1)
        };

        private readonly Stone[,] _cells;

        public GameBoard(int size = 15)
        {
            Size = size;
            _cells = new Stone[size, size];
            Reset();
        }

        public int Size { get; }

        public Stone this[int x, int y] => _cells[x, y];

        public int MoveCount { get; private set; }

        public Stone Winner { get; private set; }

        public bool IsGameOver => Winner != Stone.Empty || MoveCount >= Size * Size;

        public void Reset()
        {
            for (var x = 0; x < Size; x++)
            {
                for (var y = 0; y < Size; y++)
                {
                    _cells[x, y] = Stone.Empty;
                }
            }

            Winner = Stone.Empty;
            MoveCount = 0;
        }

        public bool IsInside(int x, int y)
        {
            return x >= 0 && x < Size && y >= 0 && y < Size;
        }

        public bool PlaceStone(int x, int y, Stone stone)
        {
            if (!IsInside(x, y) || stone == Stone.Empty || _cells[x, y] != Stone.Empty || IsGameOver)
            {
                return false;
            }

            _cells[x, y] = stone;
            MoveCount++;

            if (HasFiveInRow(x, y, stone))
            {
                Winner = stone;
            }

            return true;
        }

        public void RemoveStone(int x, int y)
        {
            if (_cells[x, y] == Stone.Empty)
            {
                return;
            }

            _cells[x, y] = Stone.Empty;
            MoveCount = Math.Max(0, MoveCount - 1);
            Winner = Stone.Empty;
        }

        public bool HasFiveInRow(int x, int y, Stone stone)
        {
            foreach (var (dx, dy) in Directions)
            {
                var count = 1;
                count += CountDirection(x, y, dx, dy, stone);
                count += CountDirection(x, y, -dx, -dy, stone);
                if (count >= 5)
                {
                    return true;
                }
            }

            return false;
        }

        public List<Move> GetCandidateMoves()
        {
            var result = new List<Move>();
            if (MoveCount == 0)
            {
                var center = Size / 2;
                result.Add(new Move(center, center));
                return result;
            }

            for (var x = 0; x < Size; x++)
            {
                for (var y = 0; y < Size; y++)
                {
                    if (_cells[x, y] != Stone.Empty || !HasNeighbor(x, y, 2))
                    {
                        continue;
                    }

                    result.Add(new Move(x, y));
                }
            }

            return result;
        }

        private int CountDirection(int x, int y, int dx, int dy, Stone stone)
        {
            var count = 0;
            var cx = x + dx;
            var cy = y + dy;

            while (IsInside(cx, cy) && _cells[cx, cy] == stone)
            {
                count++;
                cx += dx;
                cy += dy;
            }

            return count;
        }

        private bool HasNeighbor(int x, int y, int distance)
        {
            for (var dx = -distance; dx <= distance; dx++)
            {
                for (var dy = -distance; dy <= distance; dy++)
                {
                    if (dx == 0 && dy == 0)
                    {
                        continue;
                    }

                    var nx = x + dx;
                    var ny = y + dy;
                    if (IsInside(nx, ny) && _cells[nx, ny] != Stone.Empty)
                    {
                        return true;
                    }
                }
            }

            return false;
        }
    }
}
