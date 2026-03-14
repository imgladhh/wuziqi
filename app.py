from __future__ import annotations

import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from gomoku_core import BLACK, EMPTY, WHITE, GameBoard, GomokuAI
from network import NetworkPeer


BOARD_SIZE = 15
CELL_SIZE = 36
MARGIN = 32
STONE_RADIUS = 13


class GomokuApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("五子棋")
        self.root.geometry("1080x700")
        self.root.resizable(False, False)

        self.board = GameBoard(BOARD_SIZE)
        self.mode = "local_ai"
        self.current_turn = BLACK
        self.local_stone = BLACK
        self.is_my_turn = True
        self.is_thinking = False
        self.pending_undo_request = False
        self.last_opponent_move: tuple[int, int] | None = None

        self.local_button: tk.Button | None = None
        self.host_button: tk.Button | None = None
        self.join_button: tk.Button | None = None
        self.undo_button: tk.Button | None = None
        self.reset_button: tk.Button | None = None

        self.network = NetworkPeer(
            on_message=lambda message: self.root.after(0, lambda: self.handle_network_message(message)),
            on_status=lambda text: self.root.after(0, lambda: self.set_status(self.localize_network_status(text))),
            on_disconnect=lambda: self.root.after(0, self.on_disconnected),
        )

        self._build_ui()
        self.start_local_game()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        self.root.configure(bg="#efe4d2")
        try:
            self.root.tk.call("tk", "scaling", 1.0)
        except tk.TclError:
            pass

        board_wrap = tk.Frame(self.root, bg="#efe4d2")
        board_wrap.place(x=20, y=20, width=650, height=650)

        self.canvas = tk.Canvas(
            board_wrap,
            width=MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1),
            height=MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1),
            bg="#d4ad72",
            bd=0,
            highlightthickness=0,
        )
        self.canvas.place(x=10, y=10)
        self.canvas.bind("<Button-1>", self.on_board_click)

        side = tk.Frame(self.root, bg="#24404d", bd=0, highlightthickness=0)
        side.place(x=690, y=20, width=370, height=650)

        header = tk.Frame(side, bg="#1d3440")
        header.pack(fill="x")
        tk.Label(
            header,
            text="五子棋对局",
            bg="#1d3440",
            fg="#f8f4ed",
            font=("Microsoft YaHei UI", 18, "bold"),
            pady=18,
        ).pack(anchor="w", padx=24)

        self.status_var = tk.StringVar(value="准备开始")
        tk.Label(
            side,
            textvariable=self.status_var,
            bg="#24404d",
            fg="#f6d28a",
            justify="left",
            wraplength=300,
            font=("Microsoft YaHei UI", 11, "bold"),
            pady=14,
        ).pack(anchor="w", padx=24)

        info_card = self._card(side, "对局信息")
        self.mode_var = tk.StringVar(value="本地人机")
        self.stone_var = tk.StringVar(value="黑棋")
        self.turn_var = tk.StringVar(value="你先手")
        self.last_enemy_var = tk.StringVar(value="暂无")
        self.connection_var = tk.StringVar(value="未连接")
        self.host_display_var = tk.StringVar(value=self.detect_ip())
        self.port_var = tk.StringVar(value="9527")
        self._kv(info_card, "模式", self.mode_var)
        self._kv(info_card, "执子", self.stone_var)
        self._kv(info_card, "当前回合", self.turn_var)
        self._kv(info_card, "对方上一手", self.last_enemy_var)
        self._kv(info_card, "联机状态", self.connection_var)
        self._kv(info_card, "主机 IP", self.host_display_var)
        self._kv(info_card, "端口", self.port_var)

        action_card = self._card(side, "开始与控制")
        self.local_button = self._button(action_card, "本地人机", self.start_local_game)
        self.local_button.pack(fill="x", pady=(0, 8))
        self.host_button = self._button(action_card, "创建联机房间", self.start_host)
        self.host_button.pack(fill="x", pady=8)
        self.join_button = self._button(action_card, "加入联机房间", self.join_host)
        self.join_button.pack(fill="x", pady=8)
        self.undo_button = self._button(action_card, "悔棋", self.request_undo)
        self.undo_button.pack(fill="x", pady=8)
        self.reset_button = self._button(action_card, "重新开始", self.reset_current_game)
        self.reset_button.pack(fill="x", pady=(8, 0))

        setting_card = self._card(side, "连接设置")
        tk.Label(setting_card, text="主机 IP", bg="#fff9ef", fg="#264653", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.host_var = tk.StringVar(value=self.detect_ip())
        ttk.Entry(setting_card, textvariable=self.host_var).pack(fill="x", pady=(6, 10))

        tk.Label(setting_card, text="端口", bg="#fff9ef", fg="#264653", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(setting_card, textvariable=self.port_var).pack(fill="x", pady=(6, 10))

        tk.Label(setting_card, text="AI 深度", bg="#fff9ef", fg="#264653", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.depth_var = tk.StringVar(value="2")
        ttk.Combobox(setting_card, textvariable=self.depth_var, values=["2", "3"], state="readonly").pack(fill="x", pady=(6, 0))

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TEntry", fieldbackground="#fffef8", bordercolor="#c8b89b", padding=8)
        style.configure("TCombobox", fieldbackground="#fffef8", padding=6)

        self.draw_board()

    def _card(self, parent: tk.Widget, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg="#24404d")
        outer.pack(fill="x", padx=22, pady=8)
        tk.Label(
            outer,
            text=title,
            bg="#24404d",
            fg="#eec170",
            font=("Microsoft YaHei UI", 11, "bold"),
            pady=4,
        ).pack(anchor="w")
        body = tk.Frame(outer, bg="#fff9ef", padx=16, pady=12)
        body.pack(fill="x")
        return body

    def _kv(self, parent: tk.Widget, label: str, value_var: tk.StringVar) -> None:
        row = tk.Frame(parent, bg="#fff9ef")
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, width=9, anchor="w", bg="#fff9ef", fg="#7a6a58", font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Label(row, textvariable=value_var, anchor="w", bg="#fff9ef", fg="#21313c", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")

    def _button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#335c67",
            fg="white",
            activebackground="#3f7380",
            activeforeground="white",
            relief="flat",
            font=("Microsoft YaHei UI", 10, "bold"),
            pady=8,
            cursor="hand2",
        )

    def update_mode_buttons(self) -> None:
        normal_bg = "#335c67"
        normal_active = "#3f7380"
        selected_bg = "#c06014"
        selected_active = "#d97706"
        mapping = {
            self.local_button: self.mode == "local_ai",
            self.host_button: self.mode == "network" and self.local_stone == BLACK,
            self.join_button: self.mode == "network" and self.local_stone == WHITE,
        }
        for button, selected in mapping.items():
            if button is None:
                continue
            button.configure(
                bg=selected_bg if selected else normal_bg,
                activebackground=selected_active if selected else normal_active,
            )

    def draw_board(self) -> None:
        self.canvas.delete("all")
        width = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)

        self.canvas.create_rectangle(0, 0, width, width, fill="#d4ad72", outline="")
        self.canvas.create_rectangle(8, 8, width - 8, width - 8, outline="#f4e3be", width=2)

        for i in range(BOARD_SIZE):
            offset = MARGIN + i * CELL_SIZE
            self.canvas.create_line(MARGIN, offset, MARGIN + CELL_SIZE * (BOARD_SIZE - 1), offset, fill="#73542e", width=1.4)
            self.canvas.create_line(offset, MARGIN, offset, MARGIN + CELL_SIZE * (BOARD_SIZE - 1), fill="#73542e", width=1.4)

        for sx in (3, 7, 11):
            for sy in (3, 7, 11):
                cx, cy = self.to_canvas(sx, sy)
                self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#3b2f1a", outline="")

        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                stone = self.board.get(x, y)
                if stone == EMPTY:
                    continue
                cx, cy = self.to_canvas(x, y)
                if stone == BLACK:
                    self.canvas.create_oval(cx - STONE_RADIUS, cy - STONE_RADIUS, cx + STONE_RADIUS, cy + STONE_RADIUS, fill="#121212", outline="#525252", width=1.2)
                    self.canvas.create_oval(cx - 8, cy - 10, cx - 1, cy - 3, fill="#454545", outline="")
                else:
                    self.canvas.create_oval(cx - STONE_RADIUS, cy - STONE_RADIUS, cx + STONE_RADIUS, cy + STONE_RADIUS, fill="#fbfaf7", outline="#7c7c7c", width=1.2)
                    self.canvas.create_oval(cx - 7, cy - 9, cx - 1, cy - 3, fill="#ffffff", outline="")

        if self.last_opponent_move is not None and self.current_turn == self.local_stone and not self.board.is_game_over:
            cx, cy = self.to_canvas(*self.last_opponent_move)
            self.canvas.create_rectangle(cx - 18, cy - 18, cx + 18, cy + 18, outline="#d9480f", width=2)
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#d9480f", outline="")

    def to_canvas(self, x: int, y: int) -> tuple[int, int]:
        return MARGIN + x * CELL_SIZE, MARGIN + y * CELL_SIZE

    def from_canvas(self, px: int, py: int) -> tuple[int, int] | None:
        x = round((px - MARGIN) / CELL_SIZE)
        y = round((py - MARGIN) / CELL_SIZE)
        if not self.board.is_inside(x, y):
            return None
        cx, cy = self.to_canvas(x, y)
        if abs(px - cx) > CELL_SIZE / 2 or abs(py - cy) > CELL_SIZE / 2:
            return None
        return x, y

    def start_local_game(self) -> None:
        self.network.stop()
        self.mode = "local_ai"
        self.local_stone = BLACK
        self.is_my_turn = True
        self.pending_undo_request = False
        self.connection_var.set("未连接")
        self.mode_var.set("本地人机")
        self.stone_var.set("黑棋")
        self.host_display_var.set(self.detect_ip())
        self.update_mode_buttons()
        self.reset_board()
        self.set_status("本地人机模式，黑棋先手。")

    def start_host(self) -> None:
        try:
            self.mode = "network"
            self.local_stone = BLACK
            self.is_my_turn = True
            self.pending_undo_request = False
            self.mode_var.set("联机对战")
            self.stone_var.set("黑棋")
            self.connection_var.set("等待连接")
            self.host_display_var.set(self.detect_ip())
            self.update_mode_buttons()
            self.reset_board()
            self.network.start_host(int(self.port_var.get()))
            self.set_status(f"房间已创建。请将 {self.host_display_var.get()}:{self.port_var.get()} 发给朋友。")
        except Exception as exc:
            messagebox.showerror("创建失败", str(exc))

    def join_host(self) -> None:
        try:
            self.mode = "network"
            self.local_stone = WHITE
            self.is_my_turn = False
            self.pending_undo_request = False
            self.mode_var.set("联机对战")
            self.stone_var.set("白棋")
            self.connection_var.set("正在连接")
            self.host_display_var.set(self.host_var.get().strip())
            self.update_mode_buttons()
            self.reset_board()
            self.network.join_host(self.host_var.get().strip(), int(self.port_var.get()))
            self.connection_var.set("已连接")
            self.set_status("已加入房间，等待房主先手。")
            self.update_turn_display()
        except Exception as exc:
            messagebox.showerror("加入失败", str(exc))

    def reset_current_game(self) -> None:
        self.reset_board()
        if self.mode == "local_ai":
            self.set_status("本地人机模式，黑棋先手。")
            return
        self.is_my_turn = self.local_stone == BLACK
        self.pending_undo_request = False
        self.network.send("RESET")
        self.set_status("棋局已重置。")
        self.update_turn_display()

    def reset_board(self) -> None:
        self.board.reset()
        self.current_turn = BLACK
        self.is_thinking = False
        self.last_opponent_move = None
        self.last_enemy_var.set("暂无")
        self.update_turn_display()
        self.draw_board()

    def on_board_click(self, event) -> None:
        if self.board.is_game_over or self.is_thinking:
            return
        point = self.from_canvas(event.x, event.y)
        if point is None:
            return
        x, y = point

        if self.mode == "local_ai":
            if self.current_turn != self.local_stone or not self.board.place(x, y, self.local_stone):
                return
            self.last_opponent_move = None
            self.last_enemy_var.set("暂无")
            self.after_move()
            self.draw_board()
            if not self.board.is_game_over:
                self.run_ai_turn()
            return

        if not self.network.connected:
            self.set_status("联机模式下请先建立连接。")
            return
        if not self.is_my_turn or self.current_turn != self.local_stone:
            self.set_status("当前还没轮到你。")
            return
        if not self.board.place(x, y, self.local_stone):
            return
        self.network.send(f"MOVE|{x}|{y}")
        self.last_opponent_move = None
        self.last_enemy_var.set("暂无")
        self.is_my_turn = False
        self.after_move()
        self.draw_board()

    def run_ai_turn(self) -> None:
        self.is_thinking = True
        self.set_status("AI 思考中...")

        def worker() -> None:
            ai = GomokuAI(int(self.depth_var.get()))
            move = ai.best_move(self.board, WHITE)
            self.root.after(0, lambda: self.finish_ai_turn(move.x, move.y))

        threading.Thread(target=worker, daemon=True).start()

    def finish_ai_turn(self, x: int, y: int) -> None:
        if self.board.place(x, y, WHITE):
            self.last_opponent_move = (x, y)
            self.last_enemy_var.set(self.format_pos(x, y))
            self.after_move()
            self.draw_board()
        self.is_thinking = False

    def request_undo(self) -> None:
        if self.is_thinking:
            return
        if not self.board.history:
            self.set_status("当前没有可悔棋的落子。")
            return
        if self.mode == "local_ai":
            undone = self.undo_round()
            self.set_status("已悔棋。" if undone else "当前没有可悔棋的落子。")
            return
        if not self.network.connected:
            self.set_status("未连接对手，无法发起悔棋。")
            return
        if self.pending_undo_request:
            self.set_status("悔棋请求已发出，请等待对方回应。")
            return
        self.pending_undo_request = True
        self.connection_var.set("等待悔棋确认")
        self.network.send("UNDO_REQUEST")
        self.set_status("已向对方发起悔棋请求。")

    def undo_round(self) -> int:
        undone = 0
        for _ in range(2):
            move = self.board.undo_last()
            if move is None:
                break
            undone += 1
        self.current_turn = BLACK if self.board.move_count % 2 == 0 else WHITE
        self.is_my_turn = self.local_stone == self.current_turn if self.mode == "network" else self.current_turn == self.local_stone
        self.last_opponent_move = self.find_last_opponent_move()
        self.last_enemy_var.set(self.format_pos(*self.last_opponent_move) if self.last_opponent_move else "暂无")
        self.update_turn_display()
        self.draw_board()
        return undone

    def find_last_opponent_move(self) -> tuple[int, int] | None:
        enemy = WHITE if self.mode == "local_ai" or self.local_stone == BLACK else BLACK
        for x, y, stone in reversed(self.board.history):
            if stone == enemy:
                return x, y
        return None

    def after_move(self) -> None:
        if self.board.winner != EMPTY:
            if self.mode == "local_ai":
                self.set_status("你赢了。" if self.board.winner == self.local_stone else "AI 获胜。")
            else:
                self.set_status("你赢了这局。" if self.board.winner == self.local_stone else "对手获胜。")
            self.update_turn_display()
            return

        if self.board.move_count >= BOARD_SIZE * BOARD_SIZE:
            self.set_status("平局。")
            self.update_turn_display()
            return

        self.current_turn = WHITE if self.current_turn == BLACK else BLACK
        if self.mode == "local_ai":
            self.set_status("轮到你落子。" if self.current_turn == self.local_stone else "AI 回合。")
        else:
            self.set_status("轮到你落子。" if self.current_turn == self.local_stone else "等待对手落子...")
        self.update_turn_display()

    def handle_network_message(self, message: str) -> None:
        parts = message.split("|")
        command = parts[0]

        if command == "MOVE" and len(parts) == 3:
            x, y = int(parts[1]), int(parts[2])
            enemy = WHITE if self.local_stone == BLACK else BLACK
            if self.board.place(x, y, enemy):
                self.last_opponent_move = (x, y)
                self.last_enemy_var.set(self.format_pos(x, y))
                self.is_my_turn = True
                self.after_move()
                self.draw_board()
            return

        if command == "RESET":
            self.reset_board()
            self.is_my_turn = self.local_stone == BLACK
            self.pending_undo_request = False
            self.set_status("对方重开了棋局。")
            self.update_turn_display()
            return

        if command == "UNDO_REQUEST":
            self.connection_var.set("收到悔棋请求")
            approved = messagebox.askyesno("悔棋请求", "对方请求悔棋，是否同意？")
            if approved:
                self.undo_round()
                self.network.send("UNDO_ACCEPT")
                self.connection_var.set("已连接")
                self.set_status("你已同意对方悔棋。")
            else:
                self.network.send("UNDO_REJECT")
                self.connection_var.set("已连接")
                self.set_status("你拒绝了对方的悔棋请求。")
            return

        if command == "UNDO_ACCEPT":
            self.pending_undo_request = False
            self.connection_var.set("已连接")
            self.undo_round()
            self.set_status("对方已同意悔棋。")
            return

        if command == "UNDO_REJECT":
            self.pending_undo_request = False
            self.connection_var.set("已连接")
            self.set_status("对方拒绝了悔棋请求。")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def update_turn_display(self) -> None:
        if self.board.winner != EMPTY:
            self.turn_var.set("对局结束")
            return
        if self.mode == "local_ai":
            self.turn_var.set("你回合" if self.current_turn == self.local_stone else "AI 回合")
        else:
            self.turn_var.set("你回合" if self.current_turn == self.local_stone else "对方回合")

    def format_pos(self, x: int, y: int) -> str:
        return f"{x + 1},{y + 1}"

    def detect_ip(self) -> str:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                if info[0] == socket.AF_INET:
                    ip = info[4][0]
                    if not ip.startswith("127."):
                        return ip
        except OSError:
            pass
        return "127.0.0.1"

    def localize_network_status(self, text: str) -> str:
        mapping = {
            "Room created. Waiting for opponent...": "房间已创建，等待对手连接...",
            "Connected to host.": "已连接到房主。",
            "Opponent connected.": "对手已连接。",
        }
        return mapping.get(text, text)

    def on_disconnected(self) -> None:
        self.pending_undo_request = False
        self.connection_var.set("已断开")
        self.set_status("连接已断开。")

    def on_close(self) -> None:
        self.network.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    GomokuApp().run()
