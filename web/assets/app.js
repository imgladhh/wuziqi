const SIZE = 15;
const CELL = 40;
const MARGIN = 30;
const RADIUS = 13;
const POLL_MS = 1000;

const state = {
  sessionId: localStorage.getItem("wuziqi_session") || "",
  mode: "local",
  local: null,
  room: null,
  roomCode: "",
  hoverPoint: null,
};

const els = {
  board: document.getElementById("board"),
  status: document.getElementById("status"),
  modeLabel: document.getElementById("modeLabel"),
  turnLabel: document.getElementById("turnLabel"),
  lastMoveLabel: document.getElementById("lastMoveLabel"),
  roomCodeLabel: document.getElementById("roomCodeLabel"),
  linkStateLabel: document.getElementById("linkStateLabel"),
  depthSelect: document.getElementById("depthSelect"),
  startLocalBtn: document.getElementById("startLocalBtn"),
  undoLocalBtn: document.getElementById("undoLocalBtn"),
  playerNameInput: document.getElementById("playerNameInput"),
  createRoomBtn: document.getElementById("createRoomBtn"),
  copyRoomBtn: document.getElementById("copyRoomBtn"),
  roomCodeInput: document.getElementById("roomCodeInput"),
  joinRoomBtn: document.getElementById("joinRoomBtn"),
  undoRoomBtn: document.getElementById("undoRoomBtn"),
  resetRoomBtn: document.getElementById("resetRoomBtn"),
  acceptUndoBtn: document.getElementById("acceptUndoBtn"),
  rejectUndoBtn: document.getElementById("rejectUndoBtn"),
  chatMessages: document.getElementById("chatMessages"),
  chatInput: document.getElementById("chatInput"),
  sendChatBtn: document.getElementById("sendChatBtn"),
};

const ctx = els.board.getContext("2d");

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", "X-Session-Id": state.sessionId, ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  const sessionId = response.headers.get("X-Session-Id");
  if (sessionId) {
    state.sessionId = sessionId;
    localStorage.setItem("wuziqi_session", sessionId);
  }
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

function drawBoard(payload, highlight) {
  ctx.clearRect(0, 0, els.board.width, els.board.height);
  ctx.fillStyle = "#d4ad72";
  ctx.fillRect(0, 0, els.board.width, els.board.height);

  ctx.strokeStyle = "#6b4a25";
  ctx.lineWidth = 1.4;
  for (let i = 0; i < SIZE; i += 1) {
    const offset = MARGIN + i * CELL;
    ctx.beginPath();
    ctx.moveTo(MARGIN, offset);
    ctx.lineTo(MARGIN + CELL * (SIZE - 1), offset);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(offset, MARGIN);
    ctx.lineTo(offset, MARGIN + CELL * (SIZE - 1));
    ctx.stroke();
  }

  [3, 7, 11].forEach((x) => {
    [3, 7, 11].forEach((y) => {
      const [cx, cy] = toCanvas(x, y);
      ctx.fillStyle = "#3b2f1a";
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  for (let x = 0; x < SIZE; x += 1) {
    for (let y = 0; y < SIZE; y += 1) {
      const stone = payload[x][y];
      if (!stone) continue;
      const [cx, cy] = toCanvas(x, y);
      ctx.beginPath();
      ctx.arc(cx, cy, RADIUS, 0, Math.PI * 2);
      if (stone === 1) {
        ctx.fillStyle = "#111";
        ctx.fill();
        ctx.strokeStyle = "#525252";
        ctx.stroke();
      } else {
        ctx.fillStyle = "#fbfaf7";
        ctx.fill();
        ctx.strokeStyle = "#7c7c7c";
        ctx.stroke();
      }
    }
  }

  if (highlight) {
    const [cx, cy] = toCanvas(highlight[0], highlight[1]);
    ctx.strokeStyle = "#d9480f";
    ctx.lineWidth = 2;
    ctx.strokeRect(cx - 18, cy - 18, 36, 36);
    ctx.fillStyle = "#d9480f";
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  if (state.hoverPoint) {
    const [hx, hy] = state.hoverPoint;
    const [cx, cy] = toCanvas(hx, hy);
    ctx.save();
    ctx.strokeStyle = "rgba(217, 72, 15, 0.7)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 16, cy);
    ctx.lineTo(cx + 16, cy);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy - 16);
    ctx.lineTo(cx, cy + 16);
    ctx.stroke();

    const canPreview =
      (state.mode === "local" && state.local && state.local.winner === "empty" && state.local.current_turn === "black" && payload[hx][hy] === 0) ||
      (state.mode === "room" && state.room && state.room.winner === "empty" && state.room.your_turn && payload[hx][hy] === 0);
    if (canPreview) {
      ctx.globalAlpha = 0.45;
      ctx.fillStyle = state.mode === "local" ? "#111" : (state.room && state.room.your_stone === "white" ? "#fbfaf7" : "#111");
      ctx.strokeStyle = "#666";
      ctx.beginPath();
      ctx.arc(cx, cy, RADIUS, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  }
}

function toCanvas(x, y) {
  return [MARGIN + x * CELL, MARGIN + y * CELL];
}

function fromCanvas(px, py) {
  const x = Math.round((px - MARGIN) / CELL);
  const y = Math.round((py - MARGIN) / CELL);
  if (x < 0 || x >= SIZE || y < 0 || y >= SIZE) return null;
  return [x, y];
}

function formatMove(move) {
  return move ? `${move[0] + 1},${move[1] + 1}` : "None";
}

function renderChat(messages) {
  els.chatMessages.innerHTML = "";
  if (!messages || messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "chat-empty";
    empty.textContent = "No messages yet.";
    els.chatMessages.appendChild(empty);
    return;
  }

  messages.forEach((msg) => {
    const item = document.createElement("div");
    item.className = `chat-item${msg.from_you ? " self" : ""}`;

    const sender = document.createElement("div");
    sender.className = "chat-sender";
    sender.textContent = msg.from_you ? `${msg.sender} (you)` : msg.sender;

    const body = document.createElement("div");
    body.className = "chat-text";
    body.textContent = msg.text;

    item.appendChild(sender);
    item.appendChild(body);
    els.chatMessages.appendChild(item);
  });

  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

async function sendChat() {
  if (!state.roomCode) {
    return setStatus("Join or create a room first.");
  }
  const text = els.chatInput.value.trim();
  if (!text) {
    return setStatus("Message cannot be empty.");
  }
  const data = await api("/api/rooms/chat", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode, text }),
  });
  state.room = data.room;
  els.chatInput.value = "";
  setStatus("Message sent.");
  updateInfo();
}

function updateInfo() {
  if (state.mode === "local" && state.local) {
    els.modeLabel.textContent = "Local vs AI";
    if (state.local.winner !== "empty") {
      els.turnLabel.textContent = "Game Over";
      setStatus(state.local.winner === "black" ? "Player wins." : "AI wins.");
    } else {
      els.turnLabel.textContent = state.local.current_turn === "black" ? "Your turn" : "AI turn";
    }
    els.lastMoveLabel.textContent = formatMove(state.local.last_opponent_move);
    els.roomCodeLabel.textContent = "None";
    els.linkStateLabel.textContent = "Offline";
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null);
    renderChat([]);
    return;
  }

  if (state.mode === "room" && state.room) {
    els.modeLabel.textContent = "Online Room";
    if (state.room.winner !== "empty") {
      els.turnLabel.textContent = "Game Over";
      setStatus(state.room.winner === state.room.your_stone ? "Player wins." : "Opponent wins.");
    } else {
      els.turnLabel.textContent = state.room.your_turn ? "Your turn" : "Opponent turn";
    }
    els.lastMoveLabel.textContent = formatMove(state.room.opponent_last_move);
    els.roomCodeLabel.textContent = state.room.code || "None";
    if (state.room.pending_undo_request) {
      els.linkStateLabel.textContent = state.room.pending_undo_from_you ? "Waiting for undo reply" : "Undo request received";
    } else {
      els.linkStateLabel.textContent = `${state.room.connected_count}/2 connected`;
    }
    const showDecision = state.room.pending_undo_request && !state.room.pending_undo_from_you;
    els.acceptUndoBtn.classList.toggle("hidden", !showDecision);
    els.rejectUndoBtn.classList.toggle("hidden", !showDecision);
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null);
    renderChat(state.room.chat_messages || []);
    return;
  }
  renderChat([]);
}

function setStatus(text) {
  els.status.textContent = text;
}

function handleApiError(error) {
  const message = error.message || "Request failed.";
  if (message.includes("Room not found or expired")) {
    state.room = null;
    state.roomCode = "";
    els.roomCodeInput.value = "";
    els.acceptUndoBtn.classList.add("hidden");
    els.rejectUndoBtn.classList.add("hidden");
    updateInfo();
  }
  setStatus(message);
}

async function startLocal() {
  const data = await api("/api/local/new", {
    method: "POST",
    body: JSON.stringify({ depth: Number(els.depthSelect.value) }),
  });
  state.mode = "local";
  state.local = data.state;
  state.room = null;
  state.roomCode = "";
  setStatus("Local game started.");
  updateInfo();
}

async function localUndo() {
  const data = await api("/api/local/undo", { method: "POST", body: "{}" });
  state.local = data.state;
  setStatus(data.ok ? "Undo complete." : "No moves to undo.");
  updateInfo();
}

async function createRoom() {
  const name = els.playerNameInput.value.trim() || "Host";
  const data = await api("/api/rooms/create", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  state.mode = "room";
  state.room = data.room;
  state.roomCode = data.room.code;
  els.roomCodeInput.value = data.room.code;
  setStatus(`Room created: ${data.room.code}`);
  updateInfo();
}

async function joinRoom() {
  const code = els.roomCodeInput.value.trim().toUpperCase();
  const name = els.playerNameInput.value.trim() || "Player";
  const data = await api("/api/rooms/join", {
    method: "POST",
    body: JSON.stringify({ code, name }),
  });
  state.mode = "room";
  state.room = data.room;
  state.roomCode = data.room.code;
  setStatus(`Joined room: ${data.room.code}`);
  updateInfo();
}

async function roomUndo(action = "request") {
  const data = await api("/api/rooms/undo", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode, action }),
  });
  state.room = data.room;
  const labels = {
    request: "Undo request sent.",
    accept: "Undo accepted.",
    reject: "Undo rejected.",
  };
  setStatus(labels[action]);
  updateInfo();
}

async function resetRoom() {
  const data = await api("/api/rooms/reset", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode }),
  });
  state.room = data.room;
  setStatus("Room board reset.");
  updateInfo();
}

async function refresh() {
  try {
    if (state.mode === "local") {
      if (state.local && state.local.winner !== "empty") {
        updateInfo();
        return;
      }
      const data = await api("/api/local/state");
      state.local = data.state;
    } else if (state.mode === "room" && state.roomCode) {
      const data = await api(`/api/rooms/state?code=${encodeURIComponent(state.roomCode)}`);
      state.room = data.room;
    }
    updateInfo();
  } catch (error) {
    handleApiError(error);
  }
}

els.board.addEventListener("click", async (event) => {
  const rect = els.board.getBoundingClientRect();
  const scaleX = els.board.width / rect.width;
  const scaleY = els.board.height / rect.height;
  const point = fromCanvas((event.clientX - rect.left) * scaleX, (event.clientY - rect.top) * scaleY);
  if (!point) return;
  try {
    if (state.mode === "local") {
      if (state.local && state.local.winner !== "empty") {
        return setStatus("This game is over. Restart or undo to continue.");
      }
      const data = await api("/api/local/move", {
        method: "POST",
        body: JSON.stringify({ x: point[0], y: point[1] }),
      });
      state.local = data.state;
      if (state.local.winner === "empty") {
        setStatus("Move played.");
      }
      updateInfo();
      return;
    }
    if (state.mode === "room" && state.roomCode) {
      if (state.room && state.room.winner !== "empty") {
        return setStatus("This room game is over. Reset the board to continue.");
      }
      const data = await api("/api/rooms/move", {
        method: "POST",
        body: JSON.stringify({ code: state.roomCode, x: point[0], y: point[1] }),
      });
      state.room = data.room;
      if (state.room.winner === "empty") {
        setStatus("Move played.");
      }
      updateInfo();
    }
  } catch (error) {
    handleApiError(error);
  }
});

els.board.addEventListener("mousemove", (event) => {
  const rect = els.board.getBoundingClientRect();
  const scaleX = els.board.width / rect.width;
  const scaleY = els.board.height / rect.height;
  state.hoverPoint = fromCanvas((event.clientX - rect.left) * scaleX, (event.clientY - rect.top) * scaleY);
  if (state.mode === "local" && state.local) {
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null);
    return;
  }
  if (state.mode === "room" && state.room) {
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null);
    renderChat(state.room.chat_messages || []);
    return;
  }
  renderChat([]);
});

els.board.addEventListener("mouseleave", () => {
  state.hoverPoint = null;
  if (state.mode === "local" && state.local) {
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null);
    return;
  }
  if (state.mode === "room" && state.room) {
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null);
    renderChat(state.room.chat_messages || []);
    return;
  }
  renderChat([]);
});

els.startLocalBtn.addEventListener("click", () => startLocal().catch(handleApiError));
els.undoLocalBtn.addEventListener("click", () => localUndo().catch(handleApiError));
els.createRoomBtn.addEventListener("click", () => createRoom().catch(handleApiError));
els.joinRoomBtn.addEventListener("click", () => joinRoom().catch(handleApiError));
els.undoRoomBtn.addEventListener("click", () => roomUndo().catch(handleApiError));
els.resetRoomBtn.addEventListener("click", () => resetRoom().catch(handleApiError));
els.acceptUndoBtn.addEventListener("click", () => roomUndo("accept").catch(handleApiError));
els.rejectUndoBtn.addEventListener("click", () => roomUndo("reject").catch(handleApiError));
els.sendChatBtn.addEventListener("click", () => sendChat().catch(handleApiError));
els.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendChat().catch(handleApiError);
  }
});

els.copyRoomBtn.addEventListener("click", async () => {
  if (!state.roomCode) return setStatus("No room code available.");
  await navigator.clipboard.writeText(state.roomCode);
  setStatus(`Room code copied: ${state.roomCode}`);
});

startLocal().catch(handleApiError);
setInterval(refresh, POLL_MS);
