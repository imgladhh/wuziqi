from __future__ import annotations

import ctypes
import pathlib
import sys
from typing import Dict, Mapping, Optional, Sequence, Tuple


_LIBS: Dict[str, ctypes.CDLL] = {}


def load_lib(lib_path: Optional[str] = None):
    ext = ".dll" if sys.platform == "win32" else ".so"
    path = pathlib.Path(lib_path) if lib_path else pathlib.Path(__file__).resolve().parent / f"gomoku_engine{ext}"
    path = path.resolve()
    cache_key = str(path)
    if cache_key in _LIBS:
        return _LIBS[cache_key]
    if not path.exists():
        raise FileNotFoundError(f"C engine library not found: {path}")
    lib = ctypes.CDLL(str(path))
    lib.c_best_move.restype = ctypes.c_int
    lib.c_best_move.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.c_last_nodes.restype = ctypes.c_int
    lib.c_last_nodes.argtypes = []
    _LIBS[cache_key] = lib
    return lib


def c_best_move(
    board_2d: Sequence[Sequence[int]],
    size: int,
    stone: int,
    move_count: int,
    depth: int,
    time_limit_ms: float,
    weights: Mapping[str, float],
    competitive: bool = False,
    lib_path: Optional[str] = None,
) -> Tuple[int, int]:
    lib = load_lib(lib_path)
    flat_values = [int(board_2d[x][y]) for x in range(size) for y in range(size)]
    flat = (ctypes.c_uint8 * (size * size))(*flat_values)
    out_x = ctypes.c_int(-1)
    out_y = ctypes.c_int(-1)
    lib.c_best_move(
        flat,
        int(size),
        int(stone),
        int(move_count),
        int(depth),
        float(time_limit_ms),
        int(weights["score_open_four"]),
        int(weights["score_half_four"]),
        int(weights["score_open_three"]),
        int(weights["score_half_three"]),
        int(weights["score_open_two"]),
        int(weights["score_half_two"]),
        float(weights["enemy_scale"]),
        int(competitive),
        ctypes.byref(out_x),
        ctypes.byref(out_y),
    )
    return int(out_x.value), int(out_y.value)


def c_last_nodes() -> int:
    return int(load_lib().c_last_nodes())
