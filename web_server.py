from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from gomoku_core import BLACK, EMPTY, WHITE, GameBoard, GomokuAI, opponent


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "web"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))


def stone_name(stone: int) -> str:
    return {BLACK: "black", WHITE: "white"}.get(stone, "empty")


def room_code() -> str:
    return secrets.token_hex(3).upper()


def now_ts() -> int:
    return int(time.time())


@dataclass
class LocalGame:
    board: GameBoard = field(default_factory=GameBoard)
    depth: int = 2
    current_turn: int = BLACK
    last_opponent_move: Optional[tuple[int, int]] = None

    def reset(self, depth: int) -> None:
        self.board.reset()
        self.depth = depth
        self.current_turn = BLACK
        self.last_opponent_move = None


@dataclass
class Room:
    code: str
    board: GameBoard = field(default_factory=GameBoard)
    players: Dict[str, int] = field(default_factory=dict)
    names: Dict[str, str] = field(default_factory=dict)
    current_turn: int = BLACK
    pending_undo_request: Optional[str] = None
    last_move: Optional[tuple[int, int, int]] = None
    updated_at: int = field(default_factory=now_ts)

    def reset(self) -> None:
        self.board.reset()
        self.current_turn = BLACK
        self.pending_undo_request = None
        self.last_move = None
        self.updated_at = now_ts()

    def undo_round(self) -> int:
        undone = 0
        for _ in range(2):
            move = self.board.undo_last()
            if move is None:
                break
            undone += 1
        self.current_turn = BLACK if self.board.move_count % 2 == 0 else WHITE
        self.last_move = self.board.history[-1] if self.board.history else None
        self.pending_undo_request = None
        self.updated_at = now_ts()
        return undone


class GameStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.local_games: Dict[str, LocalGame] = {}
        self.rooms: Dict[str, Room] = {}

    def get_local(self, session_id: str) -> LocalGame:
        if session_id not in self.local_games:
            self.local_games[session_id] = LocalGame()
        return self.local_games[session_id]

    def create_room(self, session_id: str, name: str) -> Room:
        code = room_code()
        while code in self.rooms:
            code = room_code()
        room = Room(code=code)
        room.players[session_id] = BLACK
        room.names[session_id] = name or "房主"
        self.rooms[code] = room
        return room


STORE = GameStore()


def board_payload(board: GameBoard) -> list[list[int]]:
    return [[board.get(x, y) for y in range(board.size)] for x in range(board.size)]


def local_state_payload(game: LocalGame) -> dict[str, Any]:
    return {
        "board": board_payload(game.board),
        "winner": stone_name(game.board.winner),
        "current_turn": stone_name(game.current_turn),
        "last_opponent_move": list(game.last_opponent_move) if game.last_opponent_move else None,
        "move_count": game.board.move_count,
    }


def room_state_payload(room: Room, session_id: str) -> dict[str, Any]:
    your_stone = room.players.get(session_id, EMPTY)
    opponent_move = None
    if room.last_move and room.last_move[2] == opponent(your_stone):
        opponent_move = [room.last_move[0], room.last_move[1]]
    elif room.last_move and your_stone == EMPTY:
        opponent_move = [room.last_move[0], room.last_move[1]]

    return {
        "code": room.code,
        "board": board_payload(room.board),
        "winner": stone_name(room.board.winner),
        "current_turn": stone_name(room.current_turn),
        "your_stone": stone_name(your_stone),
        "your_turn": your_stone != EMPTY and room.current_turn == your_stone and room.board.winner == EMPTY,
        "players": {
            stone_name(stone): room.names[sid]
            for sid, stone in room.players.items()
        },
        "connected_count": len(room.players),
        "pending_undo_request": room.pending_undo_request is not None,
        "pending_undo_from_you": room.pending_undo_request == session_id,
        "opponent_last_move": opponent_move,
        "move_count": room.board.move_count,
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "WuziqiWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_file("index.html", "text/html; charset=utf-8")
        if parsed.path.startswith("/assets/"):
            rel = parsed.path[len("/assets/") :]
            return self.serve_asset(rel)
        if parsed.path == "/api/local/state":
            return self.handle_local_state()
        if parsed.path == "/api/rooms/state":
            return self.handle_room_state(parsed)
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/local/new":
            return self.handle_local_new()
        if path == "/api/local/move":
            return self.handle_local_move()
        if path == "/api/local/undo":
            return self.handle_local_undo()
        if path == "/api/rooms/create":
            return self.handle_room_create()
        if path == "/api/rooms/join":
            return self.handle_room_join()
        if path == "/api/rooms/move":
            return self.handle_room_move()
        if path == "/api/rooms/reset":
            return self.handle_room_reset()
        if path == "/api/rooms/undo":
            return self.handle_room_undo()
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def serve_asset(self, relative_path: str) -> None:
        file_path = STATIC_DIR / "assets" / relative_path
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        self.serve_raw(file_path.read_bytes(), content_type)

    def serve_file(self, name: str, content_type: str) -> None:
        file_path = STATIC_DIR / name
        self.serve_raw(file_path.read_bytes(), content_type)

    def serve_raw(self, payload: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def session_id(self) -> str:
        incoming = self.headers.get("X-Session-Id")
        return incoming if incoming else secrets.token_hex(16)

    def send_json(self, payload: dict[str, Any], status: int = 200, session_id: Optional[str] = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if session_id:
            self.send_header("X-Session-Id", session_id)
        self.end_headers()
        self.wfile.write(raw)

    def handle_local_new(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        depth = int(body.get("depth", 2))
        with STORE.lock:
            game = STORE.get_local(session_id)
            game.reset(depth)
            payload = local_state_payload(game)
        self.send_json({"ok": True, "state": payload}, session_id=session_id)

    def handle_local_state(self) -> None:
        session_id = self.session_id()
        with STORE.lock:
            payload = local_state_payload(STORE.get_local(session_id))
        self.send_json({"ok": True, "state": payload}, session_id=session_id)

    def handle_local_move(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        x, y = int(body["x"]), int(body["y"])
        with STORE.lock:
            game = STORE.get_local(session_id)
            if game.current_turn != BLACK or not game.board.place(x, y, BLACK):
                return self.send_json({"ok": False, "error": "当前无法落子。"}, 400, session_id)
            game.current_turn = WHITE
            if not game.board.is_game_over:
                ai = GomokuAI(game.depth)
                move = ai.best_move(game.board, WHITE)
                if game.board.place(move.x, move.y, WHITE):
                    game.last_opponent_move = (move.x, move.y)
                game.current_turn = BLACK
            payload = local_state_payload(game)
        self.send_json({"ok": True, "state": payload}, session_id=session_id)

    def handle_local_undo(self) -> None:
        session_id = self.session_id()
        with STORE.lock:
            game = STORE.get_local(session_id)
            undone = 0
            for _ in range(2):
                move = game.board.undo_last()
                if move is None:
                    break
                undone += 1
            game.current_turn = BLACK if game.board.move_count % 2 == 0 else WHITE
            game.last_opponent_move = None
            for x, y, stone in reversed(game.board.history):
                if stone == WHITE:
                    game.last_opponent_move = (x, y)
                    break
            payload = local_state_payload(game)
        self.send_json({"ok": undone > 0, "state": payload}, session_id=session_id)

    def handle_room_create(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        name = str(body.get("name", "房主")).strip() or "房主"
        with STORE.lock:
            room = STORE.create_room(session_id, name)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_join(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body.get("code", "")).strip().upper()
        name = str(body.get("name", "玩家")).strip() or "玩家"
        with STORE.lock:
            room = STORE.rooms.get(code)
            if room is None:
                return self.send_json({"ok": False, "error": "房间不存在。"}, 404, session_id)
            if session_id not in room.players:
                if len(room.players) >= 2:
                    return self.send_json({"ok": False, "error": "房间已满。"}, 400, session_id)
                room.players[session_id] = WHITE
                room.names[session_id] = name
                room.updated_at = now_ts()
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_state(self, parsed) -> None:
        session_id = self.session_id()
        code = parse_qs(parsed.query).get("code", [""])[0].upper()
        with STORE.lock:
            room = STORE.rooms.get(code)
            if room is None:
                return self.send_json({"ok": False, "error": "房间不存在。"}, 404, session_id)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_move(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        x, y = int(body["x"]), int(body["y"])
        with STORE.lock:
            room = STORE.rooms.get(code)
            if room is None:
                return self.send_json({"ok": False, "error": "房间不存在。"}, 404, session_id)
            stone = room.players.get(session_id, EMPTY)
            if stone == EMPTY:
                return self.send_json({"ok": False, "error": "你不在该房间中。"}, 403, session_id)
            if room.current_turn != stone or not room.board.place(x, y, stone):
                return self.send_json({"ok": False, "error": "当前无法落子。"}, 400, session_id)
            room.current_turn = opponent(stone)
            room.last_move = (x, y, stone)
            room.updated_at = now_ts()
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_reset(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        with STORE.lock:
            room = STORE.rooms.get(code)
            if room is None:
                return self.send_json({"ok": False, "error": "房间不存在。"}, 404, session_id)
            if session_id not in room.players:
                return self.send_json({"ok": False, "error": "你不在该房间中。"}, 403, session_id)
            room.reset()
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_undo(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        action = str(body["action"])
        with STORE.lock:
            room = STORE.rooms.get(code)
            if room is None:
                return self.send_json({"ok": False, "error": "房间不存在。"}, 404, session_id)
            if session_id not in room.players:
                return self.send_json({"ok": False, "error": "你不在该房间中。"}, 403, session_id)
            if action == "request":
                room.pending_undo_request = session_id
                room.updated_at = now_ts()
            elif action == "accept":
                if room.pending_undo_request is None:
                    return self.send_json({"ok": False, "error": "当前没有待处理的悔棋请求。"}, 400, session_id)
                room.undo_round()
            elif action == "reject":
                room.pending_undo_request = None
                room.updated_at = now_ts()
            else:
                return self.send_json({"ok": False, "error": "未知操作。"}, 400, session_id)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Web server running on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
