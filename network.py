from __future__ import annotations

import socket
import threading
from typing import Callable, Optional


class NetworkPeer:
    def __init__(
        self,
        on_message: Callable[[str], None],
        on_status: Callable[[str], None],
        on_disconnect: Callable[[], None],
    ) -> None:
        self.on_message = on_message
        self.on_status = on_status
        self.on_disconnect = on_disconnect
        self.listener: Optional[socket.socket] = None
        self.sock: Optional[socket.socket] = None
        self.reader = None
        self.writer = None
        self.running = False

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def start_host(self, port: int) -> None:
        self.stop()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("0.0.0.0", port))
        self.listener.listen(1)
        self.running = True
        self.on_status("Room created. Waiting for opponent...")
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def join_host(self, host: str, port: int) -> None:
        self.stop()
        client = socket.create_connection((host, port), timeout=8)
        self._attach_socket(client)
        self.on_status("Connected to host.")

    def _accept_loop(self) -> None:
        assert self.listener is not None
        try:
            client, _ = self.listener.accept()
            self._attach_socket(client)
            self.on_status("Opponent connected.")
        except OSError as exc:
            if self.running:
                self.on_status(f"Listen failed: {exc}")

    def _attach_socket(self, sock: socket.socket) -> None:
        self.sock = sock
        self.reader = sock.makefile("r", encoding="utf-8")
        self.writer = sock.makefile("w", encoding="utf-8")
        self.running = True
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        try:
            assert self.reader is not None
            while self.running:
                line = self.reader.readline()
                if not line:
                    break
                self.on_message(line.strip())
        except OSError as exc:
            if self.running:
                self.on_status(f"Connection lost: {exc}")
        finally:
            self.stop()
            self.on_disconnect()

    def send(self, text: str) -> None:
        if not self.writer:
            return
        try:
            self.writer.write(text + "\n")
            self.writer.flush()
        except OSError as exc:
            self.on_status(f"Send failed: {exc}")
            self.stop()

    def stop(self) -> None:
        self.running = False
        for stream in (self.reader, self.writer):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for sock in (self.sock, self.listener):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self.reader = None
        self.writer = None
        self.sock = None
        self.listener = None
