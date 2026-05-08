from __future__ import annotations

import pathlib
import subprocess
import sys


def main() -> None:
    here = pathlib.Path(__file__).resolve().parent
    src = here / "gomoku_engine.c"
    if sys.platform == "win32":
        out = here / "gomoku_engine.dll"
        cmd = [
            "gcc",
            "-O3",
            "-march=native",
            "-shared",
            "-o",
            str(out),
            str(src),
        ]
    else:
        out = here / "gomoku_engine.so"
        cmd = [
            "gcc",
            "-O3",
            "-march=native",
            "-shared",
            "-fPIC",
            "-o",
            str(out),
            str(src),
        ]
    subprocess.run(cmd, check=True)
    print(f"Built: {out}")


if __name__ == "__main__":
    main()
