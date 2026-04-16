const SIZE = 15;
const CELL = 40;
const MARGIN = 30;
const RADIUS = 13;
const POLL_MS = 1000;

const EMPTY = 0;
const BLACK = 1;
const WHITE = 2;

const state = {
  sessionId: localStorage.getItem("wuziqi_session") || "",
  screen: "landing",
  mode: "local",
  local: null,
  room: null,
  roomCode: "",
  hoverPoint: null,
  roomSocket: null,
  roomSocketReconnect: null,
  suppressSocketReconnect: false,
  localSocket: null,
  localSocketReconnect: null,
  suppressLocalSocketReconnect: false,
  returnToSetupTimer: null,
};

const els = {
  landingScreen: document.getElementById("landingScreen"),
  onlineSetupScreen: document.getElementById("onlineSetupScreen"),
  gameScreen: document.getElementById("gameScreen"),
  goLocalBtn: document.getElementById("goLocalBtn"),
  goOnlineBtn: document.getElementById("goOnlineBtn"),
  backToHomeFromSetupBtn: document.getElementById("backToHomeFromSetupBtn"),
  backHomeBtn: document.getElementById("backHomeBtn"),
  exitMatchBtn: document.getElementById("exitMatchBtn"),
  setupStatus: document.getElementById("setupStatus"),
  board: document.getElementById("board"),
  status: document.getElementById("status"),
  modeLabel: document.getElementById("modeLabel"),
  turnLabel: document.getElementById("turnLabel"),
  turnTimerLabel: document.getElementById("turnTimerLabel"),
  hintUsageLabel: document.getElementById("hintUsageLabel"),
  lastMoveLabel: document.getElementById("lastMoveLabel"),
  linkStateLabel: document.getElementById("linkStateLabel"),
  depthSelect: document.getElementById("depthSelect"),
  startLocalBtn: document.getElementById("startLocalBtn"),
  undoLocalBtn: document.getElementById("undoLocalBtn"),
  playerNameInput: document.getElementById("playerNameInput"),
  turnLimitSelect: document.getElementById("turnLimitSelect"),
  onlineCompetitiveMode: document.getElementById("onlineCompetitiveMode"),
  createRoomBtn: document.getElementById("createRoomBtn"),
  roomCodeInput: document.getElementById("roomCodeInput"),
  joinRoomBtn: document.getElementById("joinRoomBtn"),
  roomStatusText: document.getElementById("roomStatusText"),
  roomCodePill: document.getElementById("roomCodePill"),
  copyCreatedRoomBtn: document.getElementById("copyCreatedRoomBtn"),
  enterCreatedRoomBtn: document.getElementById("enterCreatedRoomBtn"),
  leaveSetupRoomBtn: document.getElementById("leaveSetupRoomBtn"),
  roomPlayerList: document.getElementById("roomPlayerList"),
  hintRoomBtn: document.getElementById("hintRoomBtn"),
  undoRoomBtn: document.getElementById("undoRoomBtn"),
  resetRoomBtn: document.getElementById("resetRoomBtn"),
  acceptUndoBtn: document.getElementById("acceptUndoBtn"),
  rejectUndoBtn: document.getElementById("rejectUndoBtn"),
  hintPanel: document.getElementById("hintPanel"),
  hintMoveLabel: document.getElementById("hintMoveLabel"),
  hintReasonLabel: document.getElementById("hintReasonLabel"),
  localActions: document.getElementById("localActions"),
  localCompetitiveSelect: document.getElementById("localCompetitiveSelect"),
  onlineActions: document.getElementById("onlineActions"),
  chatCard: document.getElementById("chatCard"),
  chatMessages: document.getElementById("chatMessages"),
  chatInput: document.getElementById("chatInput"),
  sendChatBtn: document.getElementById("sendChatBtn"),
};

const boardContext = els.board.getContext("2d");

function showScreen(screen) {
  state.screen = screen;
  els.landingScreen.classList.toggle("hidden", screen !== "landing");
  els.onlineSetupScreen.classList.toggle("hidden", screen !== "online-setup");
  els.gameScreen.classList.toggle("hidden", screen !== "game");
  syncPanels();
}

function setStatus(message) {
  els.status.textContent = message;
}

function setSetupStatus(message) {
  els.setupStatus.textContent = message;
}

function syncPanels() {
  const localGame = state.screen === "game" && state.mode === "local";
  const onlineGame = state.screen === "game" && state.mode === "room";
  els.localActions.classList.toggle("hidden", !localGame);
  els.onlineActions.classList.toggle("hidden", !onlineGame);
  els.chatCard.classList.toggle("hidden", !onlineGame);
  els.exitMatchBtn.classList.toggle("hidden", !onlineGame);
}

function clearReturnToSetupTimer() {
  if (state.returnToSetupTimer) {
    clearTimeout(state.returnToSetupTimer);
    state.returnToSetupTimer = null;
  }
}

function scheduleReturnToSetup(message) {
  clearReturnToSetupTimer();
  setStatus(message);
  state.returnToSetupTimer = setTimeout(() => {
    state.returnToSetupTimer = null;
    disconnectRoomSocket();
    showScreen("online-setup");
    setSetupStatus("对手已退出棋局，你已返回房间创建页面。可以重新创建或加入房间。");
    state.room = null;
    state.roomCode = "";
    els.roomCodeInput.value = "";
    updateInfo();
  }, 3000);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Session-Id": state.sessionId,
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  const sessionId = response.headers.get("X-Session-Id");
  if (sessionId) {
    state.sessionId = sessionId;
    localStorage.setItem("wuziqi_session", sessionId);
  }

  const raw = await response.text();
  let data = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch (_error) {
      throw new Error(raw.trim() || "请求失败。");
    }
  }

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "请求失败。");
  }
  return data;
}

function colorToStone(color) {
  if (color === "black") return BLACK;
  if (color === "white") return WHITE;
  return EMPTY;
}

function formatMove(move) {
  if (!move || move.length < 2) return "无";
  return `${move[0]},${move[1]}`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function boardCoordFromPoint(x, y) {
  const bx = Math.round((x - MARGIN) / CELL);
  const by = Math.round((y - MARGIN) / CELL);
  if (bx < 0 || by < 0 || bx >= SIZE || by >= SIZE) return null;
  return [bx, by];
}

function eventToBoardPoint(event) {
  const rect = els.board.getBoundingClientRect();
  const scaleX = els.board.width / rect.width;
  const scaleY = els.board.height / rect.height;
  const x = (event.clientX - rect.left) * scaleX;
  const y = (event.clientY - rect.top) * scaleY;
  return boardCoordFromPoint(x, y);
}

function drawStone(x, y, stone, alpha = 1) {
  const cx = MARGIN + x * CELL;
  const cy = MARGIN + y * CELL;
  boardContext.save();
  boardContext.globalAlpha = alpha;
  const gradient = boardContext.createRadialGradient(cx - 5, cy - 5, 3, cx, cy, RADIUS);
  if (stone === BLACK) {
    gradient.addColorStop(0, "#666");
    gradient.addColorStop(1, "#111");
  } else {
    gradient.addColorStop(0, "#ffffff");
    gradient.addColorStop(1, "#dedede");
  }
  boardContext.beginPath();
  boardContext.arc(cx, cy, RADIUS, 0, Math.PI * 2);
  boardContext.fillStyle = gradient;
  boardContext.fill();
  boardContext.restore();
}

function drawMarker(move, color) {
  if (!move) return;
  const cx = MARGIN + move[0] * CELL;
  const cy = MARGIN + move[1] * CELL;
  boardContext.save();
  boardContext.strokeStyle = color;
  boardContext.lineWidth = 3;
  boardContext.strokeRect(cx - 18, cy - 18, 36, 36);
  boardContext.restore();
}

function drawHover(move, stone) {
  if (!move) return;
  const board = currentBoard();
  if (!board || board[move[0]][move[1]] !== EMPTY) return;
  drawStone(move[0], move[1], stone, 0.35);
  const cx = MARGIN + move[0] * CELL;
  const cy = MARGIN + move[1] * CELL;
  boardContext.save();
  boardContext.strokeStyle = "rgba(24, 79, 184, 0.35)";
  boardContext.lineWidth = 1;
  boardContext.beginPath();
  boardContext.moveTo(cx - 18, cy);
  boardContext.lineTo(cx + 18, cy);
  boardContext.moveTo(cx, cy - 18);
  boardContext.lineTo(cx, cy + 18);
  boardContext.stroke();
  boardContext.restore();
}

function drawBoard(board, lastEnemyMove = null, hintMove = null) {
  boardContext.clearRect(0, 0, els.board.width, els.board.height);
  boardContext.fillStyle = "#d4ad72";
  boardContext.fillRect(0, 0, els.board.width, els.board.height);

  boardContext.strokeStyle = "#6b4a25";
  boardContext.lineWidth = 1;
  for (let i = 0; i < SIZE; i += 1) {
    const offset = MARGIN + i * CELL;
    boardContext.beginPath();
    boardContext.moveTo(MARGIN, offset);
    boardContext.lineTo(MARGIN + CELL * (SIZE - 1), offset);
    boardContext.stroke();

    boardContext.beginPath();
    boardContext.moveTo(offset, MARGIN);
    boardContext.lineTo(offset, MARGIN + CELL * (SIZE - 1));
    boardContext.stroke();
  }

  const stars = [[3, 3], [7, 3], [11, 3], [3, 7], [7, 7], [11, 7], [3, 11], [7, 11], [11, 11]];
  boardContext.fillStyle = "#4b351d";
  stars.forEach(([x, y]) => {
    boardContext.beginPath();
    boardContext.arc(MARGIN + x * CELL, MARGIN + y * CELL, 5, 0, Math.PI * 2);
    boardContext.fill();
  });

  for (let x = 0; x < SIZE; x += 1) {
    for (let y = 0; y < SIZE; y += 1) {
      const stone = board?.[x]?.[y] || EMPTY;
      if (stone !== EMPTY) drawStone(x, y, stone);
    }
  }

  drawMarker(lastEnemyMove, "#d65e1a");
  drawMarker(hintMove, "#1861d2");

  const hoverStone = state.mode === "room"
    ? colorToStone(state.room?.your_stone || "empty")
    : BLACK;
  if (hoverStone !== EMPTY) drawHover(state.hoverPoint, hoverStone);
}

function currentBoard() {
  if (state.mode === "room" && state.room) return state.room.board;
  if (state.mode === "local" && state.local) return state.local.board;
  return null;
}

function currentRoomPlayerItems() {
  if (!state.room) return [];
  const players = state.room.players || {};
  return ["black", "white"].map((stone) => {
    const name = players[stone] || "等待加入";
    const self = stone === state.room.your_stone;
    const role = stone === "black" ? "黑棋" : "白棋";
    return { stone, name, self, role };
  });
}

function renderSetupRoomCard() {
  if (!state.room) {
    els.roomStatusText.textContent = "当前还没有加入房间。";
    els.roomCodePill.classList.add("hidden");
    els.copyCreatedRoomBtn.classList.add("hidden");
    els.enterCreatedRoomBtn.disabled = true;
    els.leaveSetupRoomBtn.disabled = true;
    els.roomPlayerList.innerHTML = '<div class="muted-text">加入房间后，这里会显示双方席位。</div>';
    return;
  }

  const status = state.room.match_entered
    ? "双方已进入对局。"
    : (state.room.is_host
      ? "你是房主，可以在双方到齐后进入对局。"
      : "已加入房间，等待房主开始对局。");
  els.roomStatusText.textContent = status;
  els.roomCodePill.textContent = `房间码 ${state.room.code}`;
  els.roomCodePill.classList.remove("hidden");
  els.copyCreatedRoomBtn.classList.remove("hidden");
  els.leaveSetupRoomBtn.disabled = false;
  els.enterCreatedRoomBtn.disabled = !(state.room.is_host && state.room.connected_count >= 2 && !state.room.match_entered);

  const items = currentRoomPlayerItems();
  els.roomPlayerList.innerHTML = items.map((item) => {
    const classes = ["room-player-item"];
    if (item.self) classes.push("current-room-player");
    return `
      <div class="${classes.join(" ")}">
        <div>
          <strong>${item.name}</strong>
          <span>${item.role}${item.self ? " · 你" : ""}</span>
        </div>
        <span>${item.stone === "black" ? "先手" : "后手"}</span>
      </div>
    `;
  }).join("");
}

function renderHintPanel(hint) {
  if (!hint) {
    els.hintPanel.classList.add("hidden");
    els.hintMoveLabel.textContent = "推荐落点：无";
    els.hintReasonLabel.textContent = "你可以使用本局唯一一次 AI 提示来获取推荐落点和理由。";
    return;
  }
  els.hintPanel.classList.remove("hidden");
  els.hintMoveLabel.textContent = `推荐落点：${formatMove(hint.move)}`;
  els.hintReasonLabel.textContent = hint.reason || "AI 建议你优先走这一步。";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderChat(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    els.chatMessages.innerHTML = '<div class="chat-empty">房间消息会显示在这里。</div>';
    return;
  }

  els.chatMessages.innerHTML = messages.map((message) => {
    const classes = ["chat-item"];
    if (message.system) classes.push("system");
    if (message.from_you) classes.push("self");
    const body = message.message_type === "voice"
      ? `<audio controls preload="none" src="${message.audio_data}"></audio>`
      : `<div class="chat-text">${escapeHtml(message.text || "")}</div>`;
    return `
      <div class="${classes.join(" ")}">
        <div class="chat-meta">
          <span class="chat-sender">${escapeHtml(message.sender || "系统")}</span>
          <span class="chat-time">${formatTimestamp(message.timestamp)}</span>
        </div>
        ${body}
      </div>
    `;
  }).join("");
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function ensureGameScreenForEnteredRoom() {
  if (state.mode === "room" && state.room?.match_entered && state.screen !== "game") {
    showScreen("game");
    connectRoomSocket();
    setStatus(state.room.is_host ? "你已让双方进入对局。" : "房主已让双方进入对局。");
  }
}

function roomSocketOpen() {
  return !!state.roomSocket && state.roomSocket.readyState === WebSocket.OPEN;
}

function localSocketOpen() {
  return !!state.localSocket && state.localSocket.readyState === WebSocket.OPEN;
}

function disconnectLocalSocket({ suppressReconnect = true } = {}) {
  if (state.localSocketReconnect) {
    clearTimeout(state.localSocketReconnect);
    state.localSocketReconnect = null;
  }
  state.suppressLocalSocketReconnect = suppressReconnect;
  if (state.localSocket) {
    const socket = state.localSocket;
    state.localSocket = null;
    try {
      socket.close();
    } catch (_error) {
      // ignore
    }
  }
}

function scheduleLocalSocketReconnect() {
  if (state.localSocketReconnect || state.suppressLocalSocketReconnect || state.mode !== "local" || state.screen !== "game") {
    return;
  }
  state.localSocketReconnect = setTimeout(() => {
    state.localSocketReconnect = null;
    connectLocalSocket();
  }, 1200);
}

function handleLocalSocketMessage(payload) {
  if (payload.type === "local_state" && payload.state) {
    state.local = payload.state;
    updateInfo();
    return;
  }
  if (payload.type === "local_closed") {
    disconnectLocalSocket();
  }
}

function connectLocalSocket() {
  if (typeof WebSocket === "undefined" || !state.sessionId || state.mode !== "local" || state.screen !== "game") {
    return;
  }
  if (localSocketOpen()) return;

  disconnectLocalSocket({ suppressReconnect: false });
  state.suppressLocalSocketReconnect = false;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${location.host}/ws/local?session=${encodeURIComponent(state.sessionId)}`;
  const socket = new WebSocket(url);
  state.localSocket = socket;

  socket.addEventListener("open", () => {
    if (state.localSocket === socket) updateInfo();
  });

  socket.addEventListener("message", (event) => {
    try {
      handleLocalSocketMessage(JSON.parse(event.data));
    } catch (_error) {
      setStatus("收到了一条无效的本地实时消息。");
    }
  });

  socket.addEventListener("close", () => {
    if (state.localSocket === socket) state.localSocket = null;
    if (!state.suppressLocalSocketReconnect) {
      scheduleLocalSocketReconnect();
    }
  });
}

function disconnectRoomSocket({ suppressReconnect = true } = {}) {
  if (state.roomSocketReconnect) {
    clearTimeout(state.roomSocketReconnect);
    state.roomSocketReconnect = null;
  }
  state.suppressSocketReconnect = suppressReconnect;
  if (state.roomSocket) {
    const socket = state.roomSocket;
    state.roomSocket = null;
    try {
      socket.close();
    } catch (_error) {
      // ignore
    }
  }
}

function scheduleRoomSocketReconnect() {
  if (state.roomSocketReconnect || state.suppressSocketReconnect || state.mode !== "room" || state.screen !== "game") {
    return;
  }
  state.roomSocketReconnect = setTimeout(() => {
    state.roomSocketReconnect = null;
    connectRoomSocket();
  }, 1200);
}

function handleRoomSocketMessage(payload) {
  if (payload.type === "room_state" && payload.room) {
    state.room = payload.room;
    if (state.screen === "game" && state.mode === "room" && payload.room.connected_count < 2) {
      scheduleReturnToSetup("对手已退出棋局，3 秒后返回房间创建页面。");
    } else {
      clearReturnToSetupTimer();
    }
    ensureGameScreenForEnteredRoom();
    updateInfo();
    return;
  }

  if (payload.type === "room_closed") {
    disconnectRoomSocket();
    handleApiError(new Error(payload.error || "房间不存在或已过期。"));
  }
}

function connectRoomSocket() {
  if (typeof WebSocket === "undefined" || !state.roomCode || !state.sessionId || state.mode !== "room" || state.screen !== "game") {
    return;
  }
  if (roomSocketOpen()) return;

  disconnectRoomSocket({ suppressReconnect: false });
  state.suppressSocketReconnect = false;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${location.host}/ws?code=${encodeURIComponent(state.roomCode)}&session=${encodeURIComponent(state.sessionId)}`;
  const socket = new WebSocket(url);
  state.roomSocket = socket;

  socket.addEventListener("open", () => {
    if (state.roomSocket === socket) updateInfo();
  });

  socket.addEventListener("message", (event) => {
    try {
      handleRoomSocketMessage(JSON.parse(event.data));
    } catch (_error) {
      setStatus("收到了一条无效的实时消息。");
    }
  });

  socket.addEventListener("close", () => {
    if (state.roomSocket === socket) state.roomSocket = null;
    if (!state.suppressSocketReconnect) {
      scheduleRoomSocketReconnect();
      if (state.roomCode) setStatus("实时连接已断开，正在尝试重连。");
    }
  });
}

async function loadLocalState() {
  const payload = await api("/api/local/state", { method: "GET" });
  state.local = payload.state;
}

async function startLocal() {
  const depth = Number.parseInt(els.depthSelect.value, 10) || 2;
  const competitiveMode = els.localCompetitiveSelect.value === "on";
  const payload = await api("/api/local/new", {
    method: "POST",
    body: JSON.stringify({ depth, competitive_mode: competitiveMode }),
  });
  state.mode = "local";
  state.local = payload.state;
  state.room = null;
  state.roomCode = "";
  disconnectRoomSocket();
  disconnectLocalSocket({ suppressReconnect: false });
  clearReturnToSetupTimer();
  showScreen("game");
  setStatus("本地对局已开始。");
  connectLocalSocket();
  updateInfo();
}

async function enterLocalMode() {
  state.mode = "local";
  await loadLocalState();
  disconnectRoomSocket();
  disconnectLocalSocket({ suppressReconnect: false });
  clearReturnToSetupTimer();
  showScreen("game");
  setStatus("已进入本地模式。");
  connectLocalSocket();
  updateInfo();
}

function enterOnlineSetup() {
  state.mode = "room";
  disconnectLocalSocket();
  disconnectRoomSocket();
  clearReturnToSetupTimer();
  showScreen("online-setup");
  setSetupStatus("创建房间或输入房间码加入。");
  updateInfo();
}

async function createRoom() {
  const name = (els.playerNameInput.value || "").trim() || "房主";
  const turnLimitSeconds = Number.parseInt(els.turnLimitSelect.value, 10) || 30;
  const competitiveMode = els.onlineCompetitiveMode.value === "on";
  const payload = await api("/api/rooms/create", {
    method: "POST",
    body: JSON.stringify({ name, turn_limit_seconds: turnLimitSeconds, competitive_mode: competitiveMode }),
  });
  state.mode = "room";
  state.room = payload.room;
  state.roomCode = payload.room.code;
  els.roomCodeInput.value = payload.room.code;
  showScreen("online-setup");
  setSetupStatus(`房间已创建，房间码为 ${payload.room.code}。`);
  updateInfo();
}

async function joinRoom() {
  const name = (els.playerNameInput.value || "").trim() || "玩家";
  const code = (els.roomCodeInput.value || "").trim().toUpperCase();
  if (!code) throw new Error("请输入房间码。");
  const payload = await api("/api/rooms/join", {
    method: "POST",
    body: JSON.stringify({ name, code }),
  });
  state.mode = "room";
  state.room = payload.room;
  state.roomCode = payload.room.code;
  els.roomCodeInput.value = payload.room.code;
  showScreen("online-setup");
  setSetupStatus(payload.room.is_host ? "已进入房间。" : "已加入房间，等待房主进入对局。");
  updateInfo();
}

async function enterCreatedRoom() {
  if (!state.roomCode) throw new Error("当前没有可进入的房间。");
  const payload = await api("/api/rooms/enter", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode }),
  });
  state.room = payload.room;
  ensureGameScreenForEnteredRoom();
  updateInfo();
}

async function copyActiveRoomCode() {
  const code = state.room?.code || state.roomCode;
  if (!code) throw new Error("当前没有房间码可复制。");
  await navigator.clipboard.writeText(code);
  setSetupStatus(`房间码 ${code} 已复制。`);
}

async function leaveRoom({ silent = false } = {}) {
  if (!state.roomCode) return;
  const code = state.roomCode;
  disconnectRoomSocket();
  clearReturnToSetupTimer();
  try {
    await api("/api/rooms/leave", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
  } finally {
    state.room = null;
    state.roomCode = "";
    els.roomCodeInput.value = "";
    updateInfo();
    if (!silent) setSetupStatus("你已离开房间。");
  }
}

async function leaveSetupRoom() {
  await leaveRoom();
  showScreen("online-setup");
}

async function exitMatch() {
  await leaveRoom({ silent: true });
  showScreen("online-setup");
  setSetupStatus("你已退出棋局，已返回房间创建页面。");
  setStatus("已退出棋局。");
}

async function localUndo() {
  const payload = await api("/api/local/undo", { method: "POST" });
  state.local = payload.state;
  setStatus(payload.ok ? "已悔棋。" : "当前没有可悔的落子。");
  updateInfo();
}

async function requestRoomHint() {
  const payload = await api("/api/rooms/hint", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode }),
  });
  state.room = payload.room;
  setStatus("AI 提示已生成。");
  updateInfo();
}

async function roomUndo(action = "request") {
  const payload = await api("/api/rooms/undo", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode, action }),
  });
  state.room = payload.room;
  setStatus(action === "request" ? "已发送悔棋请求。" : "已处理悔棋请求。");
  updateInfo();
}

async function resetRoom() {
  const payload = await api("/api/rooms/reset", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode }),
  });
  state.room = payload.room;
  setStatus("棋局已重开。");
  updateInfo();
}

async function sendChat() {
  if (state.mode !== "room" || !state.roomCode) return;
  const text = (els.chatInput.value || "").trim();
  if (!text) return;
  const payload = await api("/api/rooms/chat", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode, text }),
  });
  els.chatInput.value = "";
  state.room = payload.room;
  updateInfo();
}

async function localMove(x, y) {
  const payload = await api("/api/local/move", {
    method: "POST",
    body: JSON.stringify({ x, y }),
  });
  state.local = payload.state;
  setStatus("已落子。");
  updateInfo();
}

async function roomMove(x, y) {
  const payload = await api("/api/rooms/move", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode, x, y }),
  });
  state.room = payload.room;
  setStatus("已落子。");
  updateInfo();
}

async function handleBoardClick(event) {
  const point = eventToBoardPoint(event);
  if (!point) return;
  const [x, y] = point;
  const board = currentBoard();
  if (!board || board[x][y] !== EMPTY) return;

  if (state.mode === "local") {
    if (!state.local || state.local.winner !== "empty" || state.local.current_turn !== "black") {
      throw new Error(state.local?.winner !== "empty" ? "本局已经结束。" : "当前还不能落子。");
    }
    await localMove(x, y);
    return;
  }

  if (state.mode === "room") {
    if (!state.room?.match_entered) throw new Error("房主还没有让双方进入对局。");
    if (state.room.winner !== "empty") throw new Error("本局已经结束。");
    if (!state.room.your_turn) throw new Error("当前不是你的回合。");
    await roomMove(x, y);
  }
}

function updateInfo() {
  syncPanels();
  renderSetupRoomCard();

  if (state.mode === "local" && state.local) {
    els.localCompetitiveSelect.value = state.local.competitive_mode ? "on" : "off";
    els.modeLabel.textContent = state.local.competitive_mode ? "本地人机（竞技）" : "本地人机";
    els.turnTimerLabel.textContent = "无";
    els.hintUsageLabel.textContent = "无";
    els.lastMoveLabel.textContent = formatMove(state.local.last_opponent_move);
    els.linkStateLabel.textContent = localSocketOpen() ? "本地实时同步中" : "本地离线同步";
    els.hintRoomBtn.disabled = true;
    els.hintRoomBtn.textContent = "使用 AI 提示";
    els.acceptUndoBtn.classList.add("hidden");
    els.rejectUndoBtn.classList.add("hidden");
    renderHintPanel(null);
    renderChat([]);

    if (state.local.winner !== "empty") {
      els.turnLabel.textContent = "对局结束";
      setStatus(state.local.winner === "black" ? "玩家获胜。" : "AI 获胜。");
    } else {
      els.turnLabel.textContent = state.local.current_turn === "black" ? "你回合" : "AI 回合";
    }

    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null, null);
    return;
  }

  if (state.mode === "room" && state.room) {
    els.onlineCompetitiveMode.value = state.room.competitive_mode ? "on" : "off";
    els.modeLabel.textContent = state.room.competitive_mode ? "联机对战（竞技）" : "联机对战";
    els.lastMoveLabel.textContent = formatMove(state.room.opponent_last_move);

    if (!state.room.match_entered) {
      els.turnLabel.textContent = "等待开始";
      if (state.screen === "game") {
        setStatus(state.room.connected_count < 2 ? "对手已退出棋局。" : (state.room.is_host ? "等待你点击“进入对局”。" : "等待房主让双方进入对局。"));
      }
    } else if (state.room.winner !== "empty") {
      els.turnLabel.textContent = "对局结束";
      if (state.room.win_reason === "timeout") {
        setStatus(state.room.winner === state.room.your_stone ? "你通过超时获胜。" : "你超时落败。");
      } else if (state.room.winner === state.room.your_stone) {
        setStatus("你赢了这局。");
      } else {
        setStatus("对手赢了这局。");
      }
    } else {
      els.turnLabel.textContent = state.room.your_turn ? "你回合" : "对手回合";
    }

    if (!state.room.match_entered) {
      els.turnTimerLabel.textContent = "未开始";
    } else if (state.room.timer_pause_reason === "ai-hint") {
      els.turnTimerLabel.textContent = `AI 提示暂停中（${state.room.hint_pause_remaining_seconds} 秒）`;
    } else if (state.room.turn_timer_active) {
      els.turnTimerLabel.textContent = `${state.room.turn_time_left_seconds} 秒 / ${state.room.turn_time_limit_seconds} 秒`;
    } else {
      els.turnTimerLabel.textContent = "暂停";
    }

    els.hintUsageLabel.textContent = state.room.hint_used ? "已使用" : "未使用";
    const canUseHint = state.room.match_entered && !state.room.hint_used && state.room.your_turn && state.room.winner === "empty";
    els.hintRoomBtn.disabled = !canUseHint;
    els.hintRoomBtn.textContent = state.room.hint_used ? "AI 提示已用" : "使用 AI 提示";
    renderHintPanel(state.room.active_hint || null);

    if (state.room.pending_undo_request) {
      els.linkStateLabel.textContent = state.room.pending_undo_from_you ? "已发送悔棋请求" : "收到悔棋请求";
    } else if (!state.room.match_entered) {
      els.linkStateLabel.textContent = state.room.is_host ? "等待你开始对局" : "等待房主开始对局";
    } else {
      els.linkStateLabel.textContent = roomSocketOpen() ? "实时同步中" : "正在重连";
    }

    const showDecision = state.room.pending_undo_request && !state.room.pending_undo_from_you;
    els.acceptUndoBtn.classList.toggle("hidden", !showDecision);
    els.rejectUndoBtn.classList.toggle("hidden", !showDecision);

    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null, state.room.active_hint?.move || null);
    renderChat(state.room.chat_messages || []);
    return;
  }

  els.modeLabel.textContent = "本地人机";
  els.turnLabel.textContent = "等待开始";
  els.turnTimerLabel.textContent = "无";
  els.hintUsageLabel.textContent = "无";
  els.lastMoveLabel.textContent = "无";
  els.linkStateLabel.textContent = "未连接";
  els.acceptUndoBtn.classList.add("hidden");
  els.rejectUndoBtn.classList.add("hidden");
  els.hintRoomBtn.disabled = true;
  els.hintRoomBtn.textContent = "使用 AI 提示";
  renderHintPanel(null);
  renderChat([]);
  drawBoard(Array.from({ length: SIZE }, () => Array(SIZE).fill(EMPTY)), null, null);
}

async function refresh() {
  try {
    if (state.mode === "local") {
      if (!localSocketOpen()) {
        await loadLocalState();
      }
      if (state.screen === "game") {
        connectLocalSocket();
      }
    } else if (state.mode === "room" && state.roomCode && state.screen !== "game") {
      const payload = await api(`/api/rooms/state?code=${encodeURIComponent(state.roomCode)}`, { method: "GET" });
      state.room = payload.room;
      ensureGameScreenForEnteredRoom();
    }
    if (state.mode !== "room") clearReturnToSetupTimer();
    updateInfo();
  } catch (error) {
    if (state.mode === "room" && state.roomCode) {
      handleApiError(error);
    }
  }
}

function handleApiError(error) {
  const message = error instanceof Error ? error.message : String(error);
  if (state.screen === "online-setup") {
    setSetupStatus(message);
  } else {
    setStatus(message);
  }
}

async function goToLanding() {
  if (state.mode === "room" && state.roomCode) {
    await leaveRoom({ silent: true });
  }
  disconnectRoomSocket();
  disconnectLocalSocket();
  clearReturnToSetupTimer();
  state.mode = "local";
  showScreen("landing");
  setStatus("准备开始");
  setSetupStatus("创建房间或输入房间码加入。");
  updateInfo();
}

function leaveRoomOnUnload() {
  if (!state.roomCode) return;
  const payload = JSON.stringify({ code: state.roomCode });
  try {
    navigator.sendBeacon("/api/rooms/leave", new Blob([payload], { type: "application/json" }));
  } catch (_error) {
    // ignore
  }
}

els.goLocalBtn.addEventListener("click", () => enterLocalMode().catch(handleApiError));
els.goOnlineBtn.addEventListener("click", enterOnlineSetup);
els.backToHomeFromSetupBtn.addEventListener("click", () => goToLanding().catch(handleApiError));
els.backHomeBtn.addEventListener("click", () => goToLanding().catch(handleApiError));
els.exitMatchBtn.addEventListener("click", () => exitMatch().catch(handleApiError));
els.startLocalBtn.addEventListener("click", () => startLocal().catch(handleApiError));
els.undoLocalBtn.addEventListener("click", () => localUndo().catch(handleApiError));
els.createRoomBtn.addEventListener("click", () => createRoom().catch(handleApiError));
els.joinRoomBtn.addEventListener("click", () => joinRoom().catch(handleApiError));
els.copyCreatedRoomBtn.addEventListener("click", () => copyActiveRoomCode().catch(handleApiError));
els.enterCreatedRoomBtn.addEventListener("click", () => enterCreatedRoom().catch(handleApiError));
els.leaveSetupRoomBtn.addEventListener("click", () => leaveSetupRoom().catch(handleApiError));
els.hintRoomBtn.addEventListener("click", () => requestRoomHint().catch(handleApiError));
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
els.board.addEventListener("mousemove", (event) => {
  state.hoverPoint = eventToBoardPoint(event);
  updateInfo();
});
els.board.addEventListener("mouseleave", () => {
  state.hoverPoint = null;
  updateInfo();
});
els.board.addEventListener("click", (event) => {
  handleBoardClick(event).catch(handleApiError);
});
window.addEventListener("pagehide", leaveRoomOnUnload);

showScreen("landing");
setSetupStatus("创建房间或输入房间码加入。");
setStatus("准备开始");
drawBoard(Array.from({ length: SIZE }, () => Array(SIZE).fill(EMPTY)), null, null);
updateInfo();
setInterval(refresh, POLL_MS);
