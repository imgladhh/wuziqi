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
ROOM_TTL_SECONDS = int(os.environ.get("ROOM_TTL_SECONDS", "1800"))
DEFAULT_ROOM_TURN_LIMIT_SECONDS = int(os.environ.get("ROOM_TURN_LIMIT_SECONDS", "30"))
ROOM_HINT_PAUSE_SECONDS = int(os.environ.get("ROOM_HINT_PAUSE_SECONDS", "20"))


def stone_name(stone: int) -> str:
    return {BLACK: "black", WHITE: "white"}.get(stone, "empty")


def room_code() -> str:
    return secrets.token_hex(3).upper()


def now_ts() -> int:
    return int(time.time())


def add_room_message(
    room: "Room",
    sender: str,
    text: str,
    *,
    session_id: str | None = None,
    system: bool = False,
    message_type: str = "text",
    audio_data: str = "",
    mime_type: str = "",
    duration_seconds: int = 0,
) -> None:
    room.chat_messages.append({
        "session_id": session_id,
        "sender": sender,
        "text": text[:300],
        "timestamp": now_ts(),
        "system": system,
        "message_type": message_type,
        "audio_data": audio_data,
        "mime_type": mime_type,
        "duration_seconds": duration_seconds,
    })
    if len(room.chat_messages) > 50:
        room.chat_messages = room.chat_messages[-50:]
    room.updated_at = now_ts()


def session_for_stone(room: "Room", stone: int) -> Optional[str]:
    for session_id, player_stone in room.players.items():
        if player_stone == stone:
            return session_id
    return None


def room_winner(room: "Room") -> int:
    return room.board.winner or room.timeout_winner


def room_win_reason(room: "Room") -> str:
    if room.timeout_winner != EMPTY:
        return "timeout"
    if room.board.winner != EMPTY:
        return "line"
    if room.board.move_count >= room.board.size * room.board.size:
        return "draw"
    return ""


def room_timer_active(room: "Room") -> bool:
    return len(room.players) >= 2 and room_winner(room) == EMPTY and not room_hint_pause_active(room)


def room_hint_pause_active(room: "Room") -> bool:
    return room.hint_pause_session is not None and room.hint_pause_until > now_ts()


def clear_hint_pause(room: "Room") -> None:
    room.hint_pause_session = None
    room.hint_pause_until = 0
    room.hint_pause_time_left = 0


def sync_room_hint_pause(room: "Room") -> None:
    if not room.hint_pause_session:
        return
    if room.hint_pause_until > now_ts():
        return
    remaining = room.hint_pause_time_left or room.turn_limit_seconds
    room.turn_started_at = now_ts() - max(0, room.turn_limit_seconds - remaining)
    clear_hint_pause(room)


def room_time_left(room: "Room") -> int:
    sync_room_hint_pause(room)
    if not room_timer_active(room):
        if room_hint_pause_active(room):
            return room.hint_pause_time_left or room.turn_limit_seconds
        return room.turn_limit_seconds
    elapsed = max(0, now_ts() - room.turn_started_at)
    return max(0, room.turn_limit_seconds - elapsed)


def apply_room_timeout(room: "Room") -> None:
    if not room_timer_active(room):
        return
    if room_time_left(room) > 0:
        return
    loser_stone = room.current_turn
    winner_stone = opponent(loser_stone)
    room.timeout_winner = winner_stone
    room.pending_undo_request = None
    loser_name = room.names.get(session_for_stone(room, loser_stone) or "", "A player")
    winner_name = room.names.get(session_for_stone(room, winner_stone) or "", "A player")
    add_room_message(room, "System", f"{loser_name} ran out of time. {winner_name} wins on time.", system=True)


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
    turn_started_at: int = field(default_factory=now_ts)
    turn_limit_seconds: int = DEFAULT_ROOM_TURN_LIMIT_SECONDS
    timeout_winner: int = EMPTY
    chat_messages: list[dict[str, Any]] = field(default_factory=list)
    hints_used: set[str] = field(default_factory=set)
    hint_details: Dict[str, dict[str, Any]] = field(default_factory=dict)
    hint_pause_session: Optional[str] = None
    hint_pause_until: int = 0
    hint_pause_time_left: int = 0

    def reset(self) -> None:
        self.board.reset()
        self.current_turn = BLACK
        self.pending_undo_request = None
        self.last_move = None
        self.turn_started_at = now_ts()
        self.timeout_winner = EMPTY
        self.hints_used.clear()
        self.hint_details.clear()
        clear_hint_pause(self)
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
        self.turn_started_at = now_ts()
        self.timeout_winner = EMPTY
        self.hint_details.clear()
        clear_hint_pause(self)
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

    def create_room(self, session_id: str, name: str, turn_limit_seconds: int) -> Room:
        self.prune_expired_rooms()
        code = room_code()
        while code in self.rooms:
            code = room_code()
        room = Room(code=code, turn_limit_seconds=turn_limit_seconds)
        host_name = name or "Host"
        room.players[session_id] = BLACK
        room.names[session_id] = host_name
        add_room_message(room, "System", f"Room created by {host_name}.", system=True)
        self.rooms[code] = room
        return room

    def prune_expired_rooms(self) -> None:
        expired_codes = [
            code
            for code, room in self.rooms.items()
            if now_ts() - room.updated_at > ROOM_TTL_SECONDS
        ]
        for code in expired_codes:
            self.rooms.pop(code, None)

    def get_room(self, code: str) -> Optional[Room]:
        self.prune_expired_rooms()
        return self.rooms.get(code)

    def remove_room(self, code: str) -> None:
        self.rooms.pop(code, None)


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
    sync_room_hint_pause(room)
    apply_room_timeout(room)
    your_stone = room.players.get(session_id, EMPTY)
    opponent_move = None
    if room.last_move and room.last_move[2] == opponent(your_stone):
        opponent_move = [room.last_move[0], room.last_move[1]]
    elif room.last_move and your_stone == EMPTY:
        opponent_move = [room.last_move[0], room.last_move[1]]

    return {
        "code": room.code,
        "board": board_payload(room.board),
        "winner": stone_name(room_winner(room)),
        "win_reason": room_win_reason(room),
        "current_turn": stone_name(room.current_turn),
        "your_stone": stone_name(your_stone),
        "your_turn": your_stone != EMPTY and room.current_turn == your_stone and room_winner(room) == EMPTY,
        "players": {
            stone_name(stone): room.names[sid]
            for sid, stone in room.players.items()
        },
        "connected_count": len(room.players),
        "turn_time_limit_seconds": room.turn_limit_seconds,
        "turn_time_left_seconds": room_time_left(room),
        "turn_timer_active": room_timer_active(room),
        "timer_pause_reason": "ai-hint" if room_hint_pause_active(room) else "",
        "hint_pause_remaining_seconds": max(0, room.hint_pause_until - now_ts()) if room_hint_pause_active(room) else 0,
        "pending_undo_request": room.pending_undo_request is not None,
        "pending_undo_from_you": room.pending_undo_request == session_id,
        "opponent_last_move": opponent_move,
        "move_count": room.board.move_count,
        "hint_used": session_id in room.hints_used,
        "active_hint": room.hint_details.get(session_id),
        "chat_messages": [
            {
                "sender": msg["sender"],
                "text": msg["text"],
                "timestamp": msg["timestamp"],
                "system": msg.get("system", False),
                "message_type": msg.get("message_type", "text"),
                "audio_data": msg.get("audio_data", ""),
                "mime_type": msg.get("mime_type", ""),
                "duration_seconds": msg.get("duration_seconds", 0),
                "from_you": msg.get("session_id") == session_id and not msg.get("system", False),
            }
            for msg in room.chat_messages[-50:]
        ],
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
        if path == "/api/rooms/chat":
            return self.handle_room_chat()
        if path == "/api/rooms/hint":
            return self.handle_room_hint()
        if path == "/api/rooms/leave":
            return self.handle_room_leave()
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
                return self.send_json({"ok": False, "error": "You cannot move right now."}, 400, session_id)
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
        name = str(body.get("name", "Host")).strip() or "Host"
        turn_limit_seconds = int(body.get("turn_limit_seconds", DEFAULT_ROOM_TURN_LIMIT_SECONDS))
        turn_limit_seconds = max(10, min(300, turn_limit_seconds))
        with STORE.lock:
            room = STORE.create_room(session_id, name, turn_limit_seconds)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_join(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body.get("code", "")).strip().upper()
        name = str(body.get("name", "Player")).strip() or "Player"
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            if session_id not in room.players:
                if len(room.players) >= 2:
                    return self.send_json({"ok": False, "error": "Room is full."}, 400, session_id)
                room.players[session_id] = BLACK if BLACK not in room.players.values() else WHITE
                room.names[session_id] = name
                room.turn_started_at = now_ts()
                add_room_message(room, "System", f"{name} joined the room.", system=True)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_state(self, parsed) -> None:
        session_id = self.session_id()
        code = parse_qs(parsed.query).get("code", [""])[0].upper()
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_move(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        x, y = int(body["x"]), int(body["y"])
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            apply_room_timeout(room)
            stone = room.players.get(session_id, EMPTY)
            if stone == EMPTY:
                return self.send_json({"ok": False, "error": "You are not in this room."}, 403, session_id)
            if room_winner(room) != EMPTY:
                return self.send_json({"ok": False, "error": "This game is already over."}, 400, session_id)
            if room.current_turn != stone or not room.board.place(x, y, stone):
                return self.send_json({"ok": False, "error": "You cannot move right now."}, 400, session_id)
            room.current_turn = opponent(stone)
            room.last_move = (x, y, stone)
            room.turn_started_at = now_ts()
            room.pending_undo_request = None
            room.hint_details.clear()
            clear_hint_pause(room)
            room.updated_at = now_ts()
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_reset(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            if session_id not in room.players:
                return self.send_json({"ok": False, "error": "You are not in this room."}, 403, session_id)
            room.reset()
            actor = room.names.get(session_id, "A player")
            add_room_message(room, "System", f"{actor} reset the board.", system=True)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_undo(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        action = str(body["action"])
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            if session_id not in room.players:
                return self.send_json({"ok": False, "error": "You are not in this room."}, 403, session_id)
            apply_room_timeout(room)
            if room_winner(room) != EMPTY:
                return self.send_json({"ok": False, "error": "This game is already over."}, 400, session_id)
            if action == "request":
                room.pending_undo_request = session_id
                actor = room.names.get(session_id, "A player")
                add_room_message(room, "System", f"{actor} requested an undo.", system=True)
            elif action == "accept":
                if room.pending_undo_request is None:
                    return self.send_json({"ok": False, "error": "There is no pending undo request."}, 400, session_id)
                requester = room.names.get(room.pending_undo_request, "A player")
                room.undo_round()
                actor = room.names.get(session_id, "A player")
                add_room_message(room, "System", f"{actor} accepted {requester}'s undo request.", system=True)
            elif action == "reject":
                requester = room.names.get(room.pending_undo_request, "A player") if room.pending_undo_request is not None else "A player"
                room.pending_undo_request = None
                actor = room.names.get(session_id, "A player")
                add_room_message(room, "System", f"{actor} rejected {requester}'s undo request.", system=True)
            else:
                return self.send_json({"ok": False, "error": "Unknown action."}, 400, session_id)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_hint(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            sync_room_hint_pause(room)
            apply_room_timeout(room)
            stone = room.players.get(session_id, EMPTY)
            if stone == EMPTY:
                return self.send_json({"ok": False, "error": "You are not in this room."}, 403, session_id)
            if room_winner(room) != EMPTY:
                return self.send_json({"ok": False, "error": "This game is already over."}, 400, session_id)
            if room.current_turn != stone:
                return self.send_json({"ok": False, "error": "You can only request a hint on your turn."}, 400, session_id)
            if session_id in room.hints_used:
                return self.send_json({"ok": False, "error": "You have already used your AI hint in this game."}, 400, session_id)
            ai = GomokuAI(depth=3)
            move, reason = ai.suggest_move(room.board, stone)
            room.hints_used.add(session_id)
            room.hint_details[session_id] = {
                "move": [move.x, move.y],
                "reason": reason,
            }
            room.hint_pause_session = session_id
            room.hint_pause_time_left = room_time_left(room)
            room.hint_pause_until = now_ts() + ROOM_HINT_PAUSE_SECONDS
            actor = room.names.get(session_id, "A player")
            add_room_message(room, "System", f"{actor} used their one-time AI hint.", system=True)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_chat(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body["code"]).upper()
        message_type = str(body.get("type", "text")).strip().lower() or "text"
        message_text = str(body.get("text", "")).strip()
        audio_data = str(body.get("audio_data", "")).strip()
        mime_type = str(body.get("mime_type", "")).strip()
        duration_seconds = int(body.get("duration_seconds", 0))
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": False, "error": "Room not found or expired."}, 404, session_id)
            if session_id not in room.players:
                return self.send_json({"ok": False, "error": "You are not in this room."}, 403, session_id)
            sender = room.names.get(session_id, stone_name(room.players.get(session_id, EMPTY)))
            if message_type == "voice":
                if not audio_data or not audio_data.startswith("data:audio/"):
                    return self.send_json({"ok": False, "error": "Voice message data is invalid."}, 400, session_id)
                if len(audio_data) > 1_500_000:
                    return self.send_json({"ok": False, "error": "Voice message is too large."}, 400, session_id)
                duration_seconds = max(1, min(15, duration_seconds or 1))
                add_room_message(
                    room,
                    sender,
                    f"Voice message ({duration_seconds}s)",
                    session_id=session_id,
                    message_type="voice",
                    audio_data=audio_data,
                    mime_type=mime_type[:80],
                    duration_seconds=duration_seconds,
                )
            else:
                if not message_text:
                    return self.send_json({"ok": False, "error": "Message cannot be empty."}, 400, session_id)
                add_room_message(room, sender, message_text, session_id=session_id)
            payload = room_state_payload(room, session_id)
        self.send_json({"ok": True, "room": payload}, session_id=session_id)

    def handle_room_leave(self) -> None:
        session_id = self.session_id()
        body = self.read_json()
        code = str(body.get("code", "")).strip().upper()
        with STORE.lock:
            room = STORE.get_room(code)
            if room is None:
                return self.send_json({"ok": True, "room": None}, session_id=session_id)
            stone = room.players.pop(session_id, EMPTY)
            actor = room.names.pop(session_id, "A player")
            if stone == EMPTY:
                payload = room_state_payload(room, session_id) if room.code in STORE.rooms else None
                return self.send_json({"ok": True, "room": payload}, session_id=session_id)
            if room.pending_undo_request == session_id:
                room.pending_undo_request = None
            if room.hint_pause_session == session_id:
                clear_hint_pause(room)
            room.hint_details.pop(session_id, None)
            if not room.players:
                STORE.remove_room(code)
                return self.send_json({"ok": True, "room": None}, session_id=session_id)
            room.turn_started_at = now_ts()
            add_room_message(room, "System", f"{actor} left the room.", system=True)
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
