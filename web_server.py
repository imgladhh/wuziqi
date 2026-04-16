from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import WSMsgType, web

from gomoku_core import BLACK, EMPTY, WHITE, GameBoard, GomokuAI, forbidden_reason, is_forbidden_move, opponent


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


def room_timer_active(room: "Room") -> bool:
    return len(room.players) >= 2 and room_winner(room) == EMPTY and not room_hint_pause_active(room)


def room_time_left(room: "Room") -> int:
    sync_room_hint_pause(room)
    if room_hint_pause_active(room):
        return room.hint_pause_time_left or room.turn_limit_seconds
    if not room_timer_active(room):
        return room.turn_limit_seconds
    elapsed = max(0, now_ts() - room.turn_started_at)
    return max(0, room.turn_limit_seconds - elapsed)


def apply_room_timeout(room: "Room") -> None:
    sync_room_hint_pause(room)
    if not room_timer_active(room):
        return
    if room_time_left(room) > 0:
        return
    loser_stone = room.current_turn
    winner_stone = opponent(loser_stone)
    room.timeout_winner = winner_stone
    room.pending_undo_request = None
    clear_hint_pause(room)
    loser_name = room.names.get(session_for_stone(room, loser_stone) or "", "\u73a9\u5bb6")
    winner_name = room.names.get(session_for_stone(room, winner_stone) or "", "\u73a9\u5bb6")
    add_room_message(room, "\u7cfb\u7edf", f"{loser_name} \u8d85\u65f6\u672a\u843d\u5b50\uff0c{winner_name} \u901a\u8fc7\u8d85\u65f6\u83b7\u80dc\u3002", system=True)


@dataclass
class LocalGame:
    board: GameBoard = field(default_factory=GameBoard)
    depth: int = 2
    current_turn: int = BLACK
    last_opponent_move: Optional[tuple[int, int]] = None
    competitive_mode: bool = False

    def reset(self, depth: int, competitive_mode: bool = False) -> None:
        self.board.reset()
        self.depth = depth
        self.current_turn = BLACK
        self.last_opponent_move = None
        self.competitive_mode = competitive_mode


@dataclass
class Room:
    code: str
    board: GameBoard = field(default_factory=GameBoard)
    players: Dict[str, int] = field(default_factory=dict)
    names: Dict[str, str] = field(default_factory=dict)
    host_session_id: str = ""
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
    match_entered: bool = False
    competitive_mode: bool = False

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
        self.match_entered = False
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
        self.local_clients: Dict[str, set[web.WebSocketResponse]] = {}
        self.rooms: Dict[str, Room] = {}
        self.room_clients: Dict[str, Dict[web.WebSocketResponse, str]] = {}

    def get_local(self, session_id: str) -> LocalGame:
        if session_id not in self.local_games:
            self.local_games[session_id] = LocalGame()
        return self.local_games[session_id]

    def register_local_ws(self, session_id: str, ws: web.WebSocketResponse) -> None:
        self.local_clients.setdefault(session_id, set()).add(ws)

    def unregister_local_ws(self, session_id: str, ws: web.WebSocketResponse) -> None:
        clients = self.local_clients.get(session_id)
        if not clients:
            return
        clients.discard(ws)
        if not clients:
            self.local_clients.pop(session_id, None)

    def local_client_list(self, session_id: str) -> list[web.WebSocketResponse]:
        return list(self.local_clients.get(session_id, set()))

    def create_room(self, session_id: str, name: str, turn_limit_seconds: int) -> Room:
        self.prune_expired_rooms()
        code = room_code()
        while code in self.rooms:
            code = room_code()
        room = Room(code=code, turn_limit_seconds=turn_limit_seconds, host_session_id=session_id)
        host_name = name or "\u623f\u4e3b"
        room.players[session_id] = BLACK
        room.names[session_id] = host_name
        add_room_message(room, "\u7cfb\u7edf", f"{host_name} \u521b\u5efa\u4e86\u623f\u95f4\u3002", system=True)
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

    def register_ws(self, code: str, ws: web.WebSocketResponse, session_id: str) -> None:
        self.room_clients.setdefault(code, {})[ws] = session_id

    def unregister_ws(self, code: str, ws: web.WebSocketResponse) -> None:
        clients = self.room_clients.get(code)
        if not clients:
            return
        clients.pop(ws, None)
        if not clients:
            self.room_clients.pop(code, None)

    def room_client_items(self, code: str) -> list[tuple[web.WebSocketResponse, str]]:
        return list(self.room_clients.get(code, {}).items())

    def all_client_codes(self) -> list[str]:
        return list(self.room_clients.keys())


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
        "competitive_mode": game.competitive_mode,
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
        "is_host": session_id == room.host_session_id,
        "match_entered": room.match_entered,
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
        "competitive_mode": room.competitive_mode,
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


def request_session_id(request: web.Request) -> str:
    incoming = request.headers.get("X-Session-Id") or request.query.get("session")
    return incoming if incoming else secrets.token_hex(16)


async def read_json(request: web.Request) -> dict[str, Any]:
    if request.content_length in (None, 0):
        return {}
    raw = await request.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def json_response(payload: dict[str, Any], session_id: str, status: int = 200) -> web.Response:
    response = web.json_response(payload, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))
    response.headers["X-Session-Id"] = session_id
    return response


async def index(_request: web.Request) -> web.StreamResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html", charset="utf-8")
async def local_new(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    depth = int(body.get("depth", 2))
    competitive_mode = bool(body.get("competitive_mode", False))
    with STORE.lock:
        game = STORE.get_local(session_id)
        game.reset(depth, competitive_mode=competitive_mode)
        payload = local_state_payload(game)
    await broadcast_local(session_id)
    return json_response({"ok": True, "state": payload}, session_id)


async def local_state(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    with STORE.lock:
        payload = local_state_payload(STORE.get_local(session_id))
    return json_response({"ok": True, "state": payload}, session_id)


async def local_move(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    x, y = int(body["x"]), int(body["y"])
    with STORE.lock:
        game = STORE.get_local(session_id)
        if game.competitive_mode:
            reason = forbidden_reason(game.board, x, y, BLACK)
            if reason is not None:
                reason_map = {
                    "overline": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u957f\u8fde\uff086\u5b50\u53ca\u4ee5\u4e0a\uff09\u3002",
                    "double_four": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u56db\u56db\u3002",
                    "double_three": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u4e09\u4e09\u3002",
                }
                return json_response({"ok": False, "error": reason_map.get(reason, "\u7981\u624b\uff1a\u8fd9\u4e00\u624b\u4e0d\u5408\u6cd5\u3002")}, session_id, 400)
        if game.current_turn != BLACK or not game.board.place(x, y, BLACK):
            return json_response({"ok": False, "error": "\u5f53\u524d\u65e0\u6cd5\u843d\u5b50\u3002"}, session_id, 400)
        game.current_turn = WHITE
        if not game.board.is_game_over:
            ai = GomokuAI(game.depth)
            move = ai.best_move(game.board, WHITE)
            if game.board.place(move.x, move.y, WHITE):
                game.last_opponent_move = (move.x, move.y)
            game.current_turn = BLACK
        payload = local_state_payload(game)
    await broadcast_local(session_id)
    return json_response({"ok": True, "state": payload}, session_id)


async def local_undo(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
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
    await broadcast_local(session_id)
    return json_response({"ok": undone > 0, "state": payload}, session_id)


async def websocket_local(request: web.Request) -> web.StreamResponse:
    session_id = request_session_id(request)
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)

    with STORE.lock:
        game = STORE.get_local(session_id)
        STORE.register_local_ws(session_id, ws)
        payload = local_state_payload(game)

    await ws.send_json({"type": "local_state", "state": payload})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT and msg.data == "ping":
                await ws.send_str("pong")
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        with STORE.lock:
            STORE.unregister_local_ws(session_id, ws)
    return ws


async def create_room(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    name = str(body.get("name", "\u623f\u4e3b")).strip() or "\u623f\u4e3b"
    turn_limit_seconds = int(body.get("turn_limit_seconds", DEFAULT_ROOM_TURN_LIMIT_SECONDS))
    turn_limit_seconds = max(10, min(300, turn_limit_seconds))
    competitive_mode = bool(body.get("competitive_mode", False))
    with STORE.lock:
        room = STORE.create_room(session_id, name, turn_limit_seconds)
        room.competitive_mode = competitive_mode
        payload = room_state_payload(room, session_id)
    await broadcast_room(room.code)
    return json_response({"ok": True, "room": payload}, session_id)


async def join_room(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body.get("code", "")).strip().upper()
    name = str(body.get("name", "\u73a9\u5bb6")).strip() or "\u73a9\u5bb6"
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        if session_id not in room.players:
            if len(room.players) >= 2:
                return json_response({"ok": False, "error": "\u623f\u95f4\u5df2\u6ee1\u3002"}, session_id, 400)
            room.players[session_id] = BLACK if BLACK not in room.players.values() else WHITE
            room.names[session_id] = name
            room.turn_started_at = now_ts()
            add_room_message(room, "\u7cfb\u7edf", f"{name} \u52a0\u5165\u4e86\u623f\u95f4\u3002", system=True)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_state(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    code = str(request.query.get("code", "")).strip().upper()
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        payload = room_state_payload(room, session_id)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_enter_match(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        if session_id not in room.players:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        if session_id != room.host_session_id:
            return json_response({"ok": False, "error": "\u53ea\u6709\u623f\u4e3b\u53ef\u4ee5\u5f00\u59cb\u8fdb\u5165\u5bf9\u5c40\u3002"}, session_id, 403)
        if len(room.players) < 2:
            return json_response({"ok": False, "error": "\u9700\u8981\u4e24\u540d\u73a9\u5bb6\u90fd\u52a0\u5165\u540e\u624d\u80fd\u8fdb\u5165\u5bf9\u5c40\u3002"}, session_id, 400)
        room.match_entered = True
        room.updated_at = now_ts()
        actor = room.names.get(session_id, "\u623f\u4e3b")
        add_room_message(room, "\u7cfb\u7edf", f"{actor} \u5df2\u8ba9\u53cc\u65b9\u8fdb\u5165\u5bf9\u5c40\u3002", system=True)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_move(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    x, y = int(body["x"]), int(body["y"])
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        apply_room_timeout(room)
        stone = room.players.get(session_id, EMPTY)
        if stone == EMPTY:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        if not room.match_entered:
            return json_response({"ok": False, "error": "\u623f\u4e3b\u8fd8\u6ca1\u6709\u8ba9\u53cc\u65b9\u8fdb\u5165\u5bf9\u5c40\u3002"}, session_id, 400)
        if room_winner(room) != EMPTY:
            return json_response({"ok": False, "error": "\u672c\u5c40\u5df2\u7ecf\u7ed3\u675f\u3002"}, session_id, 400)
        if room.competitive_mode and stone == BLACK:
            reason = forbidden_reason(room.board, x, y, BLACK)
            if reason is not None:
                reason_map = {
                    "overline": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u957f\u8fde\uff086\u5b50\u53ca\u4ee5\u4e0a\uff09\u3002",
                    "double_four": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u56db\u56db\u3002",
                    "double_three": "\u7981\u624b\uff1a\u9ed1\u68cb\u4e0d\u53ef\u8d70\u4e09\u4e09\u3002",
                }
                return json_response({"ok": False, "error": reason_map.get(reason, "\u7981\u624b\uff1a\u8fd9\u4e00\u624b\u4e0d\u5408\u6cd5\u3002")}, session_id, 400)
        if room.current_turn != stone or not room.board.place(x, y, stone):
            return json_response({"ok": False, "error": "\u5f53\u524d\u65e0\u6cd5\u843d\u5b50\u3002"}, session_id, 400)
        room.current_turn = opponent(stone)
        room.last_move = (x, y, stone)
        room.turn_started_at = now_ts()
        room.pending_undo_request = None
        room.hint_details.clear()
        clear_hint_pause(room)
        room.updated_at = now_ts()
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_reset(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        if session_id not in room.players:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        room.reset()
        actor = room.names.get(session_id, "\u73a9\u5bb6")
        add_room_message(room, "\u7cfb\u7edf", f"{actor} \u91cd\u5f00\u4e86\u68cb\u5c40\u3002", system=True)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_undo(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    action = str(body["action"])
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        if session_id not in room.players:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        apply_room_timeout(room)
        if room_winner(room) != EMPTY:
            return json_response({"ok": False, "error": "\u672c\u5c40\u5df2\u7ecf\u7ed3\u675f\u3002"}, session_id, 400)
        if action == "request":
            room.pending_undo_request = session_id
            actor = room.names.get(session_id, "\u73a9\u5bb6")
            add_room_message(room, "\u7cfb\u7edf", f"{actor} \u8bf7\u6c42\u6094\u68cb\u3002", system=True)
        elif action == "accept":
            if room.pending_undo_request is None:
                return json_response({"ok": False, "error": "\u5f53\u524d\u6ca1\u6709\u5f85\u5904\u7406\u7684\u6094\u68cb\u8bf7\u6c42\u3002"}, session_id, 400)
            requester = room.names.get(room.pending_undo_request, "\u73a9\u5bb6")
            room.undo_round()
            actor = room.names.get(session_id, "\u73a9\u5bb6")
            add_room_message(room, "\u7cfb\u7edf", f"{actor} \u540c\u610f\u4e86 {requester} \u7684\u6094\u68cb\u8bf7\u6c42\u3002", system=True)
        elif action == "reject":
            requester = room.names.get(room.pending_undo_request, "\u73a9\u5bb6") if room.pending_undo_request is not None else "\u73a9\u5bb6"
            room.pending_undo_request = None
            actor = room.names.get(session_id, "\u73a9\u5bb6")
            add_room_message(room, "\u7cfb\u7edf", f"{actor} \u62d2\u7edd\u4e86 {requester} \u7684\u6094\u68cb\u8bf7\u6c42\u3002", system=True)
        else:
            return json_response({"ok": False, "error": "\u672a\u77e5\u64cd\u4f5c\u3002"}, session_id, 400)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_hint(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        sync_room_hint_pause(room)
        apply_room_timeout(room)
        stone = room.players.get(session_id, EMPTY)
        if stone == EMPTY:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        if not room.match_entered:
            return json_response({"ok": False, "error": "\u623f\u4e3b\u8fd8\u6ca1\u6709\u8ba9\u53cc\u65b9\u8fdb\u5165\u5bf9\u5c40\u3002"}, session_id, 400)
        if room_winner(room) != EMPTY:
            return json_response({"ok": False, "error": "\u672c\u5c40\u5df2\u7ecf\u7ed3\u675f\u3002"}, session_id, 400)
        if room.current_turn != stone:
            return json_response({"ok": False, "error": "\u53ea\u80fd\u5728\u4f60\u7684\u56de\u5408\u8bf7\u6c42\u63d0\u793a\u3002"}, session_id, 400)
        if session_id in room.hints_used:
            return json_response({"ok": False, "error": "\u4f60\u672c\u5c40\u5df2\u7ecf\u4f7f\u7528\u8fc7 AI \u63d0\u793a\u3002"}, session_id, 400)
        remaining_before_pause = room_time_left(room)
        legal_checker = is_forbidden_move if room.competitive_mode else None
        ai = GomokuAI(depth=3, legal_move_checker=(lambda b, px, py, s: not legal_checker(b, px, py, s)) if legal_checker else None)
        move, reason = ai.suggest_move(room.board, stone)
        if room.competitive_mode and stone == BLACK and is_forbidden_move(room.board, move.x, move.y, stone):
            return json_response({"ok": False, "error": "\u5f53\u524d\u5c40\u9762\u6682\u65e0\u5408\u6cd5\u7684 AI \u5efa\u8bae\u843d\u70b9\u3002"}, session_id, 400)
        room.hints_used.add(session_id)
        room.hint_details[session_id] = {
            "move": [move.x, move.y],
            "reason": reason,
        }
        room.hint_pause_session = session_id
        room.hint_pause_time_left = remaining_before_pause
        room.hint_pause_until = now_ts() + ROOM_HINT_PAUSE_SECONDS
        actor = room.names.get(session_id, "\u73a9\u5bb6")
        add_room_message(room, "\u7cfb\u7edf", f"{actor} \u4f7f\u7528\u4e86\u672c\u5c40\u552f\u4e00\u4e00\u6b21 AI \u63d0\u793a\u3002", system=True)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_chat(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body["code"]).upper()
    message_type = str(body.get("type", "text")).strip().lower() or "text"
    message_text = str(body.get("text", "")).strip()
    audio_data = str(body.get("audio_data", "")).strip()
    mime_type = str(body.get("mime_type", "")).strip()
    duration_seconds = int(body.get("duration_seconds", 0))
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": False, "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}, session_id, 404)
        if session_id not in room.players:
            return json_response({"ok": False, "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"}, session_id, 403)
        sender = room.names.get(session_id, stone_name(room.players.get(session_id, EMPTY)))
        if message_type == "voice":
            if not audio_data or not audio_data.startswith("data:audio/"):
                return json_response({"ok": False, "error": "\u8bed\u97f3\u6d88\u606f\u6570\u636e\u65e0\u6548\u3002"}, session_id, 400)
            if len(audio_data) > 1_500_000:
                return json_response({"ok": False, "error": "\u8bed\u97f3\u6d88\u606f\u8fc7\u5927\u3002"}, session_id, 400)
            duration_seconds = max(1, min(15, duration_seconds or 1))
            add_room_message(
                room,
                sender,
                f"\u8bed\u97f3\u6d88\u606f\uff08{duration_seconds} \u79d2\uff09",
                session_id=session_id,
                message_type="voice",
                audio_data=audio_data,
                mime_type=mime_type[:80],
                duration_seconds=duration_seconds,
            )
        else:
            if not message_text:
                return json_response({"ok": False, "error": "\u6d88\u606f\u5185\u5bb9\u4e0d\u80fd\u4e3a\u7a7a\u3002"}, session_id, 400)
            add_room_message(room, sender, message_text, session_id=session_id)
        payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def room_leave(request: web.Request) -> web.Response:
    session_id = request_session_id(request)
    body = await read_json(request)
    code = str(body.get("code", "")).strip().upper()
    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            return json_response({"ok": True, "room": None}, session_id)
        stone = room.players.pop(session_id, EMPTY)
        actor = room.names.pop(session_id, "\u73a9\u5bb6")
        if stone == EMPTY:
            payload = room_state_payload(room, session_id) if room.code in STORE.rooms else None
            return json_response({"ok": True, "room": payload}, session_id)
        if room.pending_undo_request == session_id:
            room.pending_undo_request = None
        if room.hint_pause_session == session_id:
            clear_hint_pause(room)
        room.hint_details.pop(session_id, None)
        if not room.players:
            STORE.remove_room(code)
            payload = None
        else:
            if room.host_session_id == session_id:
                room.host_session_id = next(iter(room.players.keys()))
                new_host = room.names.get(room.host_session_id, "\u73a9\u5bb6")
                add_room_message(room, "\u7cfb\u7edf", f"{new_host} \u73b0\u5728\u6210\u4e3a\u65b0\u7684\u623f\u4e3b\u3002", system=True)
            room.match_entered = False
            room.turn_started_at = now_ts()
            add_room_message(room, "\u7cfb\u7edf", f"{actor} \u79bb\u5f00\u4e86\u623f\u95f4\u3002", system=True)
            payload = room_state_payload(room, session_id)
    await broadcast_room(code)
    return json_response({"ok": True, "room": payload}, session_id)


async def websocket_room(request: web.Request) -> web.StreamResponse:
    session_id = request_session_id(request)
    code = str(request.query.get("code", "")).strip().upper()
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)

    with STORE.lock:
        room = STORE.get_room(code)
        if room is None:
            await ws.send_json({"type": "room_closed", "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"})
            await ws.close()
            return ws
        if session_id not in room.players:
            await ws.send_json({"type": "room_closed", "error": "\u4f60\u4e0d\u5728\u8fd9\u4e2a\u623f\u95f4\u91cc\u3002"})
            await ws.close()
            return ws
        STORE.register_ws(code, ws, session_id)
        payload = room_state_payload(room, session_id)

    await ws.send_json({"type": "room_state", "room": payload})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_str("pong")
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        with STORE.lock:
            STORE.unregister_ws(code, ws)
    return ws


async def broadcast_room(code: str) -> None:
    with STORE.lock:
        room = STORE.get_room(code)
        clients = STORE.room_client_items(code)
        if room is None:
            payloads = [(ws, {"type": "room_closed", "error": "\u623f\u95f4\u4e0d\u5b58\u5728\u6216\u5df2\u8fc7\u671f\u3002"}) for ws, _sid in clients]
        else:
            payloads = [(ws, {"type": "room_state", "room": room_state_payload(room, sid)}) for ws, sid in clients]

    stale: list[web.WebSocketResponse] = []
    for ws, payload in payloads:
        if ws.closed:
            stale.append(ws)
            continue
        try:
            await ws.send_json(payload)
            if payload.get("type") == "room_closed":
                await ws.close()
                stale.append(ws)
        except Exception:
            stale.append(ws)

    if stale:
        with STORE.lock:
            for ws in stale:
                STORE.unregister_ws(code, ws)


async def broadcast_local(session_id: str) -> None:
    with STORE.lock:
        game = STORE.get_local(session_id)
        payload = {"type": "local_state", "state": local_state_payload(game)}
        clients = STORE.local_client_list(session_id)

    stale: list[web.WebSocketResponse] = []
    for ws in clients:
        if ws.closed:
            stale.append(ws)
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            stale.append(ws)

    if stale:
        with STORE.lock:
            for ws in stale:
                STORE.unregister_local_ws(session_id, ws)


async def room_push_loop(_app: web.Application) -> None:
    while True:
        await asyncio.sleep(1)
        for code in STORE.all_client_codes():
            await broadcast_room(code)


async def start_background_tasks(app: web.Application) -> None:
    app["room_push_task"] = asyncio.create_task(room_push_loop(app))


async def cleanup_background_tasks(app: web.Application) -> None:
    task = app.get("room_push_task")
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = web.Application()
app.router.add_get("/", index)
app.router.add_static("/assets/", path=STATIC_DIR / "assets")
app.router.add_get("/ws/local", websocket_local)
app.router.add_get("/ws", websocket_room)
app.router.add_get("/api/local/state", local_state)
app.router.add_get("/api/rooms/state", room_state)
app.router.add_post("/api/local/new", local_new)
app.router.add_post("/api/local/move", local_move)
app.router.add_post("/api/local/undo", local_undo)
app.router.add_post("/api/rooms/create", create_room)
app.router.add_post("/api/rooms/join", join_room)
app.router.add_post("/api/rooms/enter", room_enter_match)
app.router.add_post("/api/rooms/move", room_move)
app.router.add_post("/api/rooms/reset", room_reset)
app.router.add_post("/api/rooms/undo", room_undo)
app.router.add_post("/api/rooms/hint", room_hint)
app.router.add_post("/api/rooms/chat", room_chat)
app.router.add_post("/api/rooms/leave", room_leave)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)


def main() -> None:
    print(f"Web server running on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
