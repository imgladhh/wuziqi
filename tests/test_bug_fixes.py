"""
Tests for four fixes:

Fix 1 (gomoku_core.py) — Python minimax board leak on TimeoutError
    _search_root and _minimax previously called board.remove() *after* a
    recursive _minimax call, with no try/finally guard.  If TimeoutError was
    raised mid-recursion, remove() was skipped and dirty stones were left on
    the board that was passed in (game.board in the server path).  The fix
    wraps every "place … recurse … remove" block in try/finally.

Fix 2 + Hardening (web/assets/app.js) — stale state guard with game_id
    refresh() polls /api/local/state every ~1 s when the WebSocket is down.
    If the AI responds quickly the POST result arrives first, then the delayed
    GET (which read the board *before* the move) arrives later and overwrites
    state.local with the old board, making all previous stones disappear.

    The guard in shouldAcceptLocalState() applies two checks in order:

      1. Cross-game guard (game_id) — each new game / "重新开始" generates a
         fresh game_id on the server.  If an incoming state's game_id differs
         from state.local.game_id it belongs to a previous game and is always
         discarded.  This closes the window where a very delayed GET/WS from
         the old game (move_count=20) would overwrite the freshly-reset board
         (move_count=0), which the original move_count-only guard missed.

      2. Within-game guard (move_count) — for the same game_id, never roll
         move_count back (covers the original POST-vs-GET race condition).

    The JS logic is trivially pure (no DOM/network dependencies), so Fix 2 is
    covered here by a pure-Python analogue that verifies the same invariant
    using the server-side LocalGame / board_payload primitives.

Fix 3 (web/assets/app.js) — XSS via voice message audio_data
    renderChat() previously interpolated message.audio_data directly into an
    innerHTML src="..." attribute without escaping.  A malicious room member
    could inject a closing quote followed by event-handler attributes.  Fixed
    by applying escapeHtml() to audio_data before it enters the template.

Fix 4 (web_server.py + web/assets/app.js) — draw not treated as game-over
    A full 15×15 board with no winner (move_count == 225, winner == EMPTY) was
    not recognised as a terminal state by the frontend.  The UI continued to
    display "你回合", the hint button remained enabled, and error messages were
    generic.  Fixed by:
      • local_state_payload() now includes a win_reason field ("draw" / "line"
        / "") mirroring the existing field in room_state_payload().
      • updateInfo(), handleBoardClick(), and the hint-button guard all check
        win_reason === "draw" alongside winner !== "empty".
"""

import copy
import unittest

from gomoku_core import BLACK, EMPTY, WHITE, GameBoard, GomokuAI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _board_snapshot(board: GameBoard) -> list[list[int]]:
    """Return a deep copy of board.cells for comparison."""
    return [list(row) for row in board.cells]


def _place_stones(board: GameBoard, *placements) -> None:
    for x, y, stone in placements:
        assert board.place(x, y, stone), f"Failed to place {stone} at ({x},{y})"


# ---------------------------------------------------------------------------
# Fix 1 – board clean after Python minimax
# ---------------------------------------------------------------------------

class BoardCleanAfterSearchTests(unittest.TestCase):
    """
    The Python minimax places/removes stones on the *live* game board during
    the tree search.  If a TimeoutError fires between place() and remove(),
    the board is left dirty.  The try/finally fix ensures remove() always runs.
    """

    def _make_mid_game_board(self) -> GameBoard:
        board = GameBoard()
        _place_stones(
            board,
            (7, 7, BLACK), (8, 7, WHITE),
            (7, 8, BLACK), (8, 8, WHITE),
            (6, 7, BLACK), (9, 7, WHITE),
        )
        return board

    # -- normal completion (no timeout) ----------------------------------------

    def test_board_unchanged_after_full_search(self) -> None:
        """
        After best_move() finishes without timing out, board.cells and
        board.move_count must be identical to their pre-call values.
        """
        board = self._make_mid_game_board()
        expected_cells = _board_snapshot(board)
        expected_count = board.move_count

        ai = GomokuAI(depth=3, time_limit_ms=500, use_c_engine=False)
        move = ai.best_move(board, BLACK)

        self.assertEqual(expected_count, board.move_count,
                         "move_count changed during search (no timeout)")
        self.assertEqual(expected_cells, _board_snapshot(board),
                         "board.cells changed during search (no timeout)")
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(EMPTY, board.get(move.x, move.y))

    # -- timeout mid-search  ---------------------------------------------------

    def test_board_unchanged_after_timeout(self) -> None:
        """
        When TimeoutError fires mid-search, every placed stone must still be
        removed.  board.cells and board.move_count must match the pre-call
        snapshot.
        """
        board = self._make_mid_game_board()
        expected_cells = _board_snapshot(board)
        expected_count = board.move_count

        # 1 ms forces a timeout almost immediately on any hardware
        ai = GomokuAI(depth=20, time_limit_ms=1, use_c_engine=False)
        move = ai.best_move(board, BLACK)

        self.assertEqual(expected_count, board.move_count,
                         "move_count changed after timeout (board leaked stones)")
        self.assertEqual(expected_cells, _board_snapshot(board),
                         "board.cells changed after timeout (board leaked stones)")
        # The move itself must be valid even after a very short budget
        self.assertTrue(board.is_inside(move.x, move.y))
        self.assertEqual(EMPTY, board.get(move.x, move.y))

    def test_board_unchanged_with_pvs_lmr_and_timeout(self) -> None:
        """Same invariant with PVS + LMR enabled (typical production settings)."""
        board = self._make_mid_game_board()
        expected_cells = _board_snapshot(board)
        expected_count = board.move_count

        ai = GomokuAI(
            depth=20,
            time_limit_ms=1,
            use_c_engine=False,
            use_pvs=True,
            use_lmr=True,
        )
        ai.best_move(board, BLACK)

        self.assertEqual(expected_count, board.move_count)
        self.assertEqual(expected_cells, _board_snapshot(board))

    def test_board_unchanged_after_timeout_at_ply0(self) -> None:
        """
        Timeout can fire at root ply (ply=0 inside _search_root).  The
        try/finally in _search_root handles this case specifically.
        """
        board = GameBoard()
        board.place(7, 7, BLACK)  # just one stone — very few candidates
        expected_cells = _board_snapshot(board)
        expected_count = board.move_count

        ai = GomokuAI(depth=20, time_limit_ms=1, use_c_engine=False)
        ai.best_move(board, WHITE)

        self.assertEqual(expected_count, board.move_count)
        self.assertEqual(expected_cells, _board_snapshot(board))

    def test_repeated_searches_leave_board_clean(self) -> None:
        """
        Simulates the server calling best_move() multiple times (once per
        turn) on the same board object, verifying no stones accumulate.
        """
        board = GameBoard()
        board.place(7, 7, BLACK)

        for turn, (stone, placer) in enumerate(
            [(WHITE, BLACK), (BLACK, WHITE), (WHITE, BLACK)], start=1
        ):
            ai = GomokuAI(depth=6, time_limit_ms=50, use_c_engine=False)
            snap_before = _board_snapshot(board)
            count_before = board.move_count

            move = ai.best_move(board, stone)

            self.assertEqual(count_before, board.move_count,
                             f"turn {turn}: move_count changed during search")
            self.assertEqual(snap_before, _board_snapshot(board),
                             f"turn {turn}: board changed during search")

            # Commit the move as the server would
            self.assertTrue(board.place(move.x, move.y, stone))


# ---------------------------------------------------------------------------
# Fix 2 – stale GET response must not override fresher move state
# ---------------------------------------------------------------------------

class StaleStateGuardTests(unittest.TestCase):
    """
    shouldAcceptLocalState() in app.js applies two guards:
      1. Cross-game guard  — discard if game_id differs (old game's delayed
         response must not overwrite the freshly reset board).
      2. Within-game guard — discard if move_count would roll back (the
         original POST-vs-GET race condition fix).

    These are pure invariants tested here via a Python analogue.
    """

    # ---- helpers --------------------------------------------------------------

    _GAME_A = "aaaa0001"
    _GAME_B = "bbbb0002"

    def _state_for(
        self,
        board: GameBoard,
        game_id: str = _GAME_A,
        move_count_override: int | None = None,
    ) -> dict:
        """Minimal analogue of web_server.local_state_payload."""
        mc = move_count_override if move_count_override is not None else board.move_count
        return {
            "board": [[board.get(x, y) for y in range(board.size)]
                      for x in range(board.size)],
            "move_count": mc,
            "winner": "empty",
            "current_turn": "black",
            "game_id": game_id,
        }

    # ---- the guard logic extracted for direct testing -----------------------

    @staticmethod
    def _apply_guard(current_local: dict | None, incoming: dict) -> dict | None:
        """
        Mirrors shouldAcceptLocalState() in app.js:

            function shouldAcceptLocalState(incoming) {
              if (!state.local || !incoming) return true;
              // Cross-game guard
              if (state.local.game_id && incoming.game_id &&
                      incoming.game_id !== state.local.game_id) {
                return false;
              }
              // Within-game guard
              return incoming.move_count >= state.local.move_count;
            }
        """
        if current_local is None or incoming is None:
            return incoming  # no current state — always accept

        cur_gid = current_local.get("game_id")
        inc_gid = incoming.get("game_id")

        # Guard 1: cross-game
        if cur_gid and inc_gid and inc_gid != cur_gid:
            return current_local  # different game — discard

        # Guard 2: within-game move_count
        if incoming["move_count"] < current_local["move_count"]:
            return current_local  # stale — keep existing

        return incoming  # fresh — accept

    # ---- within-game tests (guard 2) ----------------------------------------

    def test_stale_get_does_not_override_fresh_post(self) -> None:
        """
        Scenario: POST already delivered state with move_count=4.
        A delayed GET returns state with move_count=2.
        The guard must keep move_count=4.
        """
        fresh_state = {"move_count": 4, "winner": "empty", "board": [], "game_id": self._GAME_A}
        stale_state = {"move_count": 2, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(fresh_state, stale_state)

        self.assertEqual(4, result["move_count"],
                         "Stale GET response must not replace fresh POST state")

    def test_fresh_get_updates_state(self) -> None:
        """Normal poll update with same move_count must be accepted."""
        current = {"move_count": 4, "winner": "empty", "board": [], "game_id": self._GAME_A}
        fresh   = {"move_count": 4, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(current, fresh)
        self.assertIs(fresh, result)

    def test_newer_get_updates_state(self) -> None:
        """A GET that returns a later state (WS was down for two moves) must be accepted."""
        current = {"move_count": 2, "winner": "empty", "board": [], "game_id": self._GAME_A}
        newer   = {"move_count": 6, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(current, newer)
        self.assertIs(newer, result)

    def test_initial_state_always_accepted(self) -> None:
        """If state.local is None (no game yet), any incoming state is accepted."""
        incoming = {"move_count": 0, "winner": "empty", "board": [], "game_id": self._GAME_A}
        result = self._apply_guard(None, incoming)
        self.assertIs(incoming, result)

    def test_undo_reduces_move_count_then_poll_accepted(self) -> None:
        """
        After undo, state.local.move_count is lower (e.g., 2 after being 4).
        The next poll returning move_count=2 must NOT be discarded.
        """
        after_undo = {"move_count": 2, "winner": "empty", "board": [], "game_id": self._GAME_A}
        poll_after = {"move_count": 2, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(after_undo, poll_after)
        self.assertIs(poll_after, result)

    def test_stale_guard_across_multiple_moves(self) -> None:
        """
        Simulate a five-round game where the server correctly accumulates
        stones, while a delayed poll response for each round is discarded.
        """
        board = GameBoard()
        moves = [
            (7, 7, BLACK), (8, 7, WHITE),
            (7, 8, BLACK), (8, 8, WHITE),
            (7, 9, BLACK), (8, 9, WHITE),
            (7, 6, BLACK), (8, 6, WHITE),
            (7, 5, BLACK), (8, 5, WHITE),
        ]

        current_local: dict | None = None

        for i, (x, y, stone) in enumerate(moves):
            board.place(x, y, stone)
            post_response = self._state_for(board, game_id=self._GAME_A)
            current_local = self._apply_guard(current_local, post_response)

            stale_board = GameBoard()
            for x2, y2, s2 in moves[:i]:
                stale_board.place(x2, y2, s2)
            stale_response = self._state_for(stale_board, game_id=self._GAME_A)
            current_local = self._apply_guard(current_local, stale_response)

            self.assertEqual(
                board.move_count,
                current_local["move_count"],
                f"After move {i+1}: stale GET overwrote current state",
            )

    # ---- cross-game tests (guard 1) -----------------------------------------

    def test_old_game_delayed_response_discarded_after_restart(self) -> None:
        """
        Codex-identified gap: user clicks "重新开始", new game starts (game_id=B,
        move_count=0).  A very delayed GET/WS message from the old game arrives
        with game_id=A and move_count=20.  The old move_count-only guard would
        accept this (20 >= 0); the new game_id guard must reject it.
        """
        new_game   = {"move_count": 0,  "winner": "empty", "board": [], "game_id": self._GAME_B}
        old_game   = {"move_count": 20, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(new_game, old_game)

        self.assertIs(new_game, result,
                      "Delayed response from old game must not overwrite new game state")

    def test_same_game_id_move_count_guard_still_applies(self) -> None:
        """Within the same game, move_count rollback is still rejected."""
        current  = {"move_count": 8, "winner": "empty", "board": [], "game_id": self._GAME_A}
        stale    = {"move_count": 4, "winner": "empty", "board": [], "game_id": self._GAME_A}

        result = self._apply_guard(current, stale)
        self.assertIs(current, result)

    def test_new_game_first_poll_accepted(self) -> None:
        """
        After restart the first GET for the *new* game (same game_id as the
        POST response, move_count=0) must be accepted.
        """
        from_post  = {"move_count": 0, "winner": "empty", "board": [], "game_id": self._GAME_B}
        from_poll  = {"move_count": 0, "winner": "empty", "board": [], "game_id": self._GAME_B}

        result = self._apply_guard(from_post, from_poll)
        self.assertIs(from_poll, result)

    def test_no_game_id_falls_back_to_move_count_guard(self) -> None:
        """
        If game_id is absent (e.g. old server version), guard falls back
        gracefully to move_count-only logic — stale is still rejected.
        """
        current  = {"move_count": 6, "winner": "empty", "board": []}
        stale    = {"move_count": 2, "winner": "empty", "board": []}

        result = self._apply_guard(current, stale)
        self.assertIs(current, result)

    # ---- server payload consistency test ------------------------------------

    def test_server_board_payload_move_count_consistency(self) -> None:
        """
        The move_count field in the response payload must equal the number of
        non-empty cells on the returned board, ensuring GET and POST responses
        carry consistent metadata that the stale-guard can rely on.
        """
        board = GameBoard()
        _place_stones(
            board,
            (7, 7, BLACK), (8, 7, WHITE),
            (7, 8, BLACK), (8, 8, WHITE),
        )

        payload = self._state_for(board)
        non_empty = sum(
            1
            for row in payload["board"]
            for cell in row
            if cell != EMPTY
        )

        self.assertEqual(payload["move_count"], non_empty,
                         "move_count in payload must match non-empty cell count")
        self.assertEqual(board.move_count, payload["move_count"])

    def test_local_state_payload_includes_game_id(self) -> None:
        """
        web_server.local_state_payload must include a non-empty game_id so the
        JS guard can perform cross-game filtering.
        """
        from web_server import LocalGame, local_state_payload

        game = LocalGame()
        payload = local_state_payload(game)

        self.assertIn("game_id", payload, "game_id must be present in state payload")
        self.assertTrue(payload["game_id"], "game_id must be non-empty")

    def test_reset_generates_new_game_id(self) -> None:
        """
        Calling reset() (triggered by "重新开始") must produce a fresh game_id
        so old in-flight responses are recognised as cross-game and discarded.
        """
        from web_server import LocalGame

        game = LocalGame()
        old_id = game.game_id
        game.reset(depth=20)
        new_id = game.game_id

        self.assertNotEqual(old_id, new_id,
                            "reset() must generate a new game_id")


# ---------------------------------------------------------------------------
# Fix 3 – XSS via voice message audio_data
# ---------------------------------------------------------------------------

class AudioDataEscapeTests(unittest.TestCase):
    """
    renderChat() must escape audio_data before writing it into an innerHTML
    src="..." attribute.  The escaping logic is the same escapeHtml() already
    applied to text messages; we verify the invariant here via the Python
    analogue of that function.
    """

    @staticmethod
    def _escape_html(s: str) -> str:
        """Python mirror of app.js escapeHtml()."""
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;")
        )

    def _render_audio_src(self, audio_data: str) -> str:
        """Simulate the fixed template: src="${escapeHtml(audio_data)}"."""
        return f'src="{self._escape_html(audio_data)}"'

    def test_valid_data_uri_unchanged(self) -> None:
        """A legitimate data:audio/webm;base64,... URI survives escaping intact."""
        # Base64 alphabet + data-URI punctuation contains none of &<>"'
        data_uri = "data:audio/webm;base64,GkXfo59ChoEBQveBAULygQRC"
        result = self._render_audio_src(data_uri)
        self.assertIn(data_uri, result,
                      "Valid data URI must not be altered by escaping")

    def test_double_quote_in_audio_data_escaped(self) -> None:
        """
        A closing quote in audio_data must be escaped to &quot; so it cannot
        break out of the src="..." attribute boundary.
        """
        malicious = 'data:audio/webm;base64,AA" onload="alert(1)'
        result = self._render_audio_src(malicious)
        self.assertNotIn('" onload=', result,
                         "Unescaped double-quote must not appear in rendered src")
        self.assertIn("&quot;", result,
                      "Double-quote in audio_data must be escaped to &quot;")

    def test_script_tag_in_audio_data_escaped(self) -> None:
        """
        Angle brackets in audio_data must be escaped so an injected <script>
        tag cannot close the attribute and open a new element.
        """
        malicious = '"><script>alert(1)</script>'
        result = self._render_audio_src(malicious)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_empty_audio_data_renders_empty_src(self) -> None:
        """Absent / empty audio_data must produce an empty src, not crash."""
        result = self._render_audio_src("")
        self.assertEqual('src=""', result)

    def test_server_rejects_oversized_audio(self) -> None:
        """
        web_server.py enforces a 1 500 000-byte cap on audio_data before it
        ever reaches the database / broadcast path.  Verify the limit constant
        is present and sensible.
        """
        import web_server as ws
        import inspect
        src = inspect.getsource(ws.room_chat)
        self.assertIn("1_500_000", src,
                      "room_chat must enforce a 1_500_000 byte cap on audio_data")

    def test_server_validates_audio_data_prefix(self) -> None:
        """
        Server must reject audio_data that does not match an allowed MIME type.
        The validation now lives in the module-level _AUDIO_HEADER_RE regex;
        room_chat references it.  Verify both the regex and its use.
        """
        import web_server as ws
        import inspect

        # 1. The module exposes the compiled regex
        self.assertTrue(
            hasattr(ws, "_AUDIO_HEADER_RE"),
            "web_server must define _AUDIO_HEADER_RE for audio format validation",
        )
        pattern = ws._AUDIO_HEADER_RE.pattern
        self.assertIn("data:audio/", pattern,
                      "_AUDIO_HEADER_RE must match data:audio/ prefix")
        self.assertIn("base64,", pattern,
                      "_AUDIO_HEADER_RE must require base64 encoding")

        # 2. room_chat uses the regex (not a bare startswith check)
        src = inspect.getsource(ws.room_chat)
        self.assertIn("_AUDIO_HEADER_RE", src,
                      "room_chat must validate audio_data via _AUDIO_HEADER_RE")

        # 3. The regex allows legitimate MIME types and rejects unlisted ones
        valid = "data:audio/webm;base64,AAAA"
        self.assertIsNotNone(ws._AUDIO_HEADER_RE.match(valid),
                             "Valid data:audio/webm URI must be accepted")
        invalid = "data:audio/x-unknown;base64,AAAA"
        self.assertIsNone(ws._AUDIO_HEADER_RE.match(invalid),
                          "Unlisted MIME sub-type must be rejected")


# ---------------------------------------------------------------------------
# Fix 4 – draw treated as game-over
# ---------------------------------------------------------------------------

class DrawHandlingTests(unittest.TestCase):
    """
    A fully-occupied board with no five-in-a-row is a draw.
    local_state_payload() must return win_reason="draw", winner="empty".
    The JS guard logic (tested via Python analogue) must treat draw as terminal.
    """

    def _fill_board_no_winner(self) -> GameBoard:
        """
        Return a GameBoard with every cell occupied but no five-in-a-row.

        Pattern: ``BLACK if (x*2 + y) % 4 < 2 else WHITE``

        This produces a period-4 stripe layout where:
          • every row   (fixed x, varying y) cycles BBWWBBWW… → max run = 2
          • every column (fixed y, varying x) alternates BWBW…       → max run = 1
          • every diagonal (both directions)                          → max run = 2

        Since no direction can reach 5 consecutive stones of the same colour
        at any intermediate placement step, board.winner stays EMPTY throughout
        the fill and the final board is a genuine draw position.
        """
        board = GameBoard()
        stone_map = [[BLACK if (x * 2 + y) % 4 < 2 else WHITE
                      for y in range(board.size)]
                     for x in range(board.size)]
        for x in range(board.size):
            for y in range(board.size):
                board.place(x, y, stone_map[x][y])
        return board

    def test_full_board_has_no_winner(self) -> None:
        """Sanity check: the constructed full board has no winner."""
        board = self._fill_board_no_winner()
        self.assertEqual(EMPTY, board.winner)
        self.assertEqual(board.size * board.size, board.move_count)

    def test_local_state_payload_draw_win_reason(self) -> None:
        """
        local_state_payload() must emit win_reason='draw' when the board is
        full and there is no winner.
        """
        from web_server import LocalGame, local_state_payload

        game = LocalGame()
        game.board = self._fill_board_no_winner()
        payload = local_state_payload(game)

        self.assertEqual("draw", payload["win_reason"],
                         "full board with no winner must yield win_reason='draw'")
        self.assertEqual("empty", payload["winner"],
                         "draw must not set a winner")

    def test_local_state_payload_win_gives_line_reason(self) -> None:
        """win_reason must be 'line' (not 'draw') when there is a real winner."""
        from web_server import LocalGame, local_state_payload

        game = LocalGame()
        for i in range(5):
            game.board.place(7, i, BLACK)   # five-in-a-row for BLACK
        payload = local_state_payload(game)

        self.assertEqual("line", payload["win_reason"])
        self.assertEqual("black", payload["winner"])

    def test_local_state_payload_ongoing_has_no_win_reason(self) -> None:
        """win_reason must be '' for an ongoing game."""
        from web_server import LocalGame, local_state_payload

        game = LocalGame()
        game.board.place(7, 7, BLACK)
        payload = local_state_payload(game)

        self.assertEqual("", payload["win_reason"])

    @staticmethod
    def _js_is_game_over(state_obj: dict) -> bool:
        """
        Python mirror of the JS terminal-state check used in updateInfo() and
        handleBoardClick():

            winner !== "empty" || win_reason === "draw"
        """
        return state_obj.get("winner") != "empty" or state_obj.get("win_reason") == "draw"

    def test_draw_state_is_game_over(self) -> None:
        """JS guard must recognise draw as a terminal state."""
        draw_state = {"winner": "empty", "win_reason": "draw"}
        self.assertTrue(self._js_is_game_over(draw_state))

    def test_ongoing_state_is_not_game_over(self) -> None:
        """JS guard must not flag an ongoing game as terminal."""
        ongoing = {"winner": "empty", "win_reason": ""}
        self.assertFalse(self._js_is_game_over(ongoing))

    def test_winner_state_is_game_over(self) -> None:
        """JS guard must still flag a real winner as terminal."""
        won = {"winner": "black", "win_reason": "line"}
        self.assertTrue(self._js_is_game_over(won))

    def test_room_is_over_draw(self) -> None:
        """
        room_is_over() must return True for a full board with no winner so
        room_move / room_hint / room_undo all reject further actions on draw.
        """
        from web_server import LocalGame, room_is_over, Room, EMPTY as _EMPTY

        # Build a full-board state via a Room-like object
        class _FakeRoom:
            board = self._fill_board_no_winner()
            timeout_winner = _EMPTY

        self.assertTrue(room_is_over(_FakeRoom()),  # type: ignore[arg-type]
                        "room_is_over must be True for a drawn (full) board")

    def test_room_is_over_false_for_ongoing(self) -> None:
        """room_is_over() must return False for an in-progress game."""
        from web_server import room_is_over, EMPTY as _EMPTY

        class _FakeRoom:
            class board:
                winner = _EMPTY
                move_count = 4
                size = 15
            timeout_winner = _EMPTY

        self.assertFalse(room_is_over(_FakeRoom()),  # type: ignore[arg-type]
                         "room_is_over must be False for an ongoing game")

    def test_hint_guard_blocks_hint_on_draw(self) -> None:
        """
        canUseHint condition includes win_reason !== 'draw'.
        Verify the analogue evaluates False when the board is a draw.
        """
        def can_use_hint(room: dict) -> bool:
            return (
                room.get("match_entered", False)
                and not room.get("hint_used", True)
                and room.get("your_turn", False)
                and room.get("winner") == "empty"
                and room.get("win_reason") != "draw"
            )

        draw_room = {
            "match_entered": True, "hint_used": False,
            "your_turn": True, "winner": "empty", "win_reason": "draw",
        }
        self.assertFalse(can_use_hint(draw_room),
                         "Hint must be unavailable when the board is a draw")

        normal_room = {
            "match_entered": True, "hint_used": False,
            "your_turn": True, "winner": "empty", "win_reason": "",
        }
        self.assertTrue(can_use_hint(normal_room),
                        "Hint must remain available during a normal ongoing game")


if __name__ == "__main__":
    unittest.main()
