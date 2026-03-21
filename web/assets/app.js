const SIZE = 15;
const CELL = 40;
const MARGIN = 30;
const RADIUS = 13;
const POLL_MS = 1000;

const state = {
  sessionId: localStorage.getItem("wuziqi_session") || "",
  screen: "landing",
  mode: "local",
  local: null,
  room: null,
  roomCode: "",
  hoverPoint: null,
  leavingRoom: false,
  mediaRecorder: null,
  voiceChunks: [],
  voiceStartAt: 0,
  voiceTimer: null,
};

const els = {
  landingScreen: document.getElementById("landingScreen"),
  onlineSetupScreen: document.getElementById("onlineSetupScreen"),
  gameScreen: document.getElementById("gameScreen"),
  goLocalBtn: document.getElementById("goLocalBtn"),
  goOnlineBtn: document.getElementById("goOnlineBtn"),
  backToHomeFromSetupBtn: document.getElementById("backToHomeFromSetupBtn"),
  backHomeBtn: document.getElementById("backHomeBtn"),
  setupStatus: document.getElementById("setupStatus"),
  board: document.getElementById("board"),
  status: document.getElementById("status"),
  modeLabel: document.getElementById("modeLabel"),
  turnLabel: document.getElementById("turnLabel"),
  turnTimerLabel: document.getElementById("turnTimerLabel"),
  hintUsageLabel: document.getElementById("hintUsageLabel"),
  lastMoveLabel: document.getElementById("lastMoveLabel"),
  roomCodeLabel: document.getElementById("roomCodeLabel"),
  linkStateLabel: document.getElementById("linkStateLabel"),
  depthSelect: document.getElementById("depthSelect"),
  startLocalBtn: document.getElementById("startLocalBtn"),
  undoLocalBtn: document.getElementById("undoLocalBtn"),
  playerNameInput: document.getElementById("playerNameInput"),
  turnLimitSelect: document.getElementById("turnLimitSelect"),
  createRoomBtn: document.getElementById("createRoomBtn"),
  copyRoomBtn: document.getElementById("copyRoomBtn"),
  roomCodeInput: document.getElementById("roomCodeInput"),
  joinRoomBtn: document.getElementById("joinRoomBtn"),
  hintRoomBtn: document.getElementById("hintRoomBtn"),
  undoRoomBtn: document.getElementById("undoRoomBtn"),
  resetRoomBtn: document.getElementById("resetRoomBtn"),
  acceptUndoBtn: document.getElementById("acceptUndoBtn"),
  rejectUndoBtn: document.getElementById("rejectUndoBtn"),
  hintPanel: document.getElementById("hintPanel"),
  hintMoveLabel: document.getElementById("hintMoveLabel"),
  hintReasonLabel: document.getElementById("hintReasonLabel"),
  localActions: document.getElementById("localActions"),
  onlineActions: document.getElementById("onlineActions"),
  chatCard: document.getElementById("chatCard"),
  chatMessages: document.getElementById("chatMessages"),
  chatInput: document.getElementById("chatInput"),
  sendChatBtn: document.getElementById("sendChatBtn"),
  recordVoiceBtn: null,
  voiceStatus: null,
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

function showScreen(screen) {
  state.screen = screen;
  els.landingScreen.classList.toggle("hidden", screen !== "landing");
  els.onlineSetupScreen.classList.toggle("hidden", screen !== "online-setup");
  els.gameScreen.classList.toggle("hidden", screen !== "game");
}

function syncPanels() {
  const isLocalGame = state.screen === "game" && state.mode === "local";
  const isOnlineGame = state.screen === "game" && state.mode === "room";
  els.localActions.classList.toggle("hidden", !isLocalGame);
  els.onlineActions.classList.toggle("hidden", !isOnlineGame);
  els.chatCard.classList.toggle("hidden", !isOnlineGame);
}

function drawBoard(payload, highlight, hintMove = null) {
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

  if (hintMove) {
    const [cx, cy] = toCanvas(hintMove[0], hintMove[1]);
    ctx.save();
    ctx.strokeStyle = "#1769aa";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(cx - 20, cy - 20, 40, 40);
    ctx.setLineDash([]);
    ctx.fillStyle = "#1769aa";
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
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

function formatHintMove(move) {
  return move ? `Suggested move: ${move[0] + 1},${move[1] + 1}` : "Suggested move: None";
}

function renderHintPanel(hint) {
  if (!els.hintPanel) {
    return;
  }
  if (!hint || !hint.move) {
    els.hintPanel.classList.add("hidden");
    els.hintMoveLabel.textContent = "Suggested move: None";
    els.hintReasonLabel.textContent = "Use your one-time hint to get an AI-recommended move and reason.";
    return;
  }
  els.hintPanel.classList.remove("hidden");
  els.hintMoveLabel.textContent = formatHintMove(hint.move);
  els.hintReasonLabel.textContent = hint.reason || "The AI found a strong move for this position.";
}

function setStatus(text) {
  els.status.textContent = text;
}

function setSetupStatus(text) {
  els.setupStatus.textContent = text;
}

function setVoiceStatus(text) {
  ensureVoiceControls();
  els.voiceStatus.textContent = text;
}

function ensureVoiceControls() {
  if (els.recordVoiceBtn && els.voiceStatus) {
    return;
  }
  const toolbar = els.chatCard.querySelector(".chat-toolbar");
  if (!toolbar) {
    return;
  }

  const row = document.createElement("div");
  row.className = "inline voice-row";

  const button = document.createElement("button");
  button.type = "button";
  button.id = "recordVoiceBtn";
  button.className = "accent";
  button.textContent = "Record Voice";

  const status = document.createElement("div");
  status.id = "voiceStatus";
  status.className = "voice-status";
  status.textContent = "Up to 15 seconds per clip.";

  row.appendChild(button);
  row.appendChild(status);
  toolbar.appendChild(row);

  els.recordVoiceBtn = button;
  els.voiceStatus = status;

  button.addEventListener("click", () => toggleVoiceRecording().catch(handleApiError));
}

function renderChat(messages) {
  ensureVoiceControls();
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
    item.className = `chat-item${msg.system ? " system" : ""}${msg.from_you ? " self" : ""}`;

    const meta = document.createElement("div");
    meta.className = "chat-meta";

    const sender = document.createElement("div");
    sender.className = "chat-sender";
    sender.textContent = msg.system ? "System" : (msg.from_you ? `${msg.sender} (you)` : msg.sender);

    const time = document.createElement("div");
    time.className = "chat-time";
    time.textContent = new Date((msg.timestamp || 0) * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    const body = document.createElement("div");
    body.className = "chat-text";
    if (msg.message_type === "voice" && msg.audio_data) {
      const label = document.createElement("div");
      label.textContent = msg.text || "Voice message";
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "metadata";
      audio.src = msg.audio_data;
      body.appendChild(label);
      body.appendChild(audio);
    } else {
      body.textContent = msg.text;
    }

    meta.appendChild(sender);
    meta.appendChild(time);
    item.appendChild(meta);
    item.appendChild(body);
    els.chatMessages.appendChild(item);
  });

  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read recorded audio."));
    reader.readAsDataURL(blob);
  });
}

function stopVoiceUi() {
  if (state.voiceTimer) {
    window.clearInterval(state.voiceTimer);
    state.voiceTimer = null;
  }
  if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  if (els.recordVoiceBtn) {
    els.recordVoiceBtn.textContent = "Record Voice";
  }
}

async function startVoiceRecording() {
  if (!state.roomCode) {
    throw new Error("Join or create a room first.");
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("This browser does not support microphone recording.");
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "";
  const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

  state.mediaRecorder = recorder;
  state.voiceChunks = [];
  state.voiceStartAt = Date.now();

  recorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      state.voiceChunks.push(event.data);
    }
  });

  recorder.addEventListener("stop", async () => {
    const durationSeconds = Math.max(1, Math.min(15, Math.round((Date.now() - state.voiceStartAt) / 1000)));
    const chunks = state.voiceChunks.slice();
    state.mediaRecorder = null;
    state.voiceChunks = [];
    stopVoiceUi();
    stream.getTracks().forEach((track) => track.stop());

    if (chunks.length === 0) {
      setVoiceStatus("Recording cancelled.");
      return;
    }

    try {
      setVoiceStatus("Uploading voice clip...");
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const audioData = await blobToDataUrl(blob);
      const data = await api("/api/rooms/chat", {
        method: "POST",
        body: JSON.stringify({
          code: state.roomCode,
          type: "voice",
          audio_data: audioData,
          mime_type: recorder.mimeType || "audio/webm",
          duration_seconds: durationSeconds,
        }),
      });
      state.room = data.room;
      setStatus("Voice message sent.");
      setVoiceStatus("Voice clip sent.");
      updateInfo();
    } catch (error) {
      setVoiceStatus("Voice upload failed.");
      handleApiError(error);
    }
  });

  recorder.start();
  if (els.recordVoiceBtn) {
    els.recordVoiceBtn.textContent = "Stop Recording";
  }
  setVoiceStatus("Recording... 15s left");
  state.voiceTimer = window.setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.voiceStartAt) / 1000);
    const left = Math.max(0, 15 - elapsed);
    setVoiceStatus(`Recording... ${left}s left`);
    if (left <= 0 && state.mediaRecorder && state.mediaRecorder.state === "recording") {
      state.mediaRecorder.stop();
    }
  }, 250);
}

async function toggleVoiceRecording() {
  ensureVoiceControls();
  if (typeof MediaRecorder === "undefined") {
    throw new Error("This browser does not support voice recording.");
  }
  if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  await startVoiceRecording();
}

function updateInfo() {
  syncPanels();

  if (state.mode === "local" && state.local) {
    els.modeLabel.textContent = "Local vs AI";
    if (state.local.winner !== "empty") {
      els.turnLabel.textContent = "Game Over";
      setStatus(state.local.winner === "black" ? "Player wins." : "AI wins.");
    } else {
      els.turnLabel.textContent = state.local.current_turn === "black" ? "Your turn" : "AI turn";
    }
    els.turnTimerLabel.textContent = "None";
    els.hintUsageLabel.textContent = "N/A";
    if (els.hintRoomBtn) {
      els.hintRoomBtn.disabled = true;
      els.hintRoomBtn.textContent = "Use AI Hint";
    }
    renderHintPanel(null);
    els.lastMoveLabel.textContent = formatMove(state.local.last_opponent_move);
    els.roomCodeLabel.textContent = "None";
    els.linkStateLabel.textContent = "Offline";
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null, null);
    renderChat([]);
    return;
  }

  if (state.mode === "room" && state.room) {
    els.modeLabel.textContent = "Online Room";
    if (state.room.winner !== "empty") {
      els.turnLabel.textContent = "Game Over";
      if (state.room.win_reason === "timeout") {
        setStatus(state.room.winner === state.room.your_stone ? "You win on time." : "You lose on time.");
      } else {
        setStatus(state.room.winner === state.room.your_stone ? "Player wins." : "Opponent wins.");
      }
    } else {
      els.turnLabel.textContent = state.room.your_turn ? "Your turn" : "Opponent turn";
    }
    els.turnTimerLabel.textContent = state.room.timer_pause_reason === "ai-hint"
      ? `Paused for AI hint (${state.room.hint_pause_remaining_seconds}s)`
      : (state.room.turn_timer_active
        ? `${state.room.turn_time_left_seconds}s / ${state.room.turn_time_limit_seconds}s`
        : "Paused");
    els.hintUsageLabel.textContent = state.room.hint_used ? "Used" : "Available";
    if (els.hintRoomBtn) {
      const canUseHint = !state.room.hint_used && state.room.your_turn && state.room.winner === "empty";
      els.hintRoomBtn.disabled = !canUseHint;
      els.hintRoomBtn.textContent = state.room.hint_used ? "AI Hint Used" : "Use AI Hint";
    }
    renderHintPanel(state.room.active_hint || null);
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
    const suggestedMove = state.room.active_hint ? state.room.active_hint.move : null;
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null, suggestedMove);
    renderChat(state.room.chat_messages || []);
    return;
  }

  els.turnTimerLabel.textContent = "None";
  els.hintUsageLabel.textContent = "None";
  renderHintPanel(null);
  if (els.hintRoomBtn) {
    els.hintRoomBtn.disabled = true;
    els.hintRoomBtn.textContent = "Use AI Hint";
  }
  els.lastMoveLabel.textContent = "None";
  els.roomCodeLabel.textContent = "None";
  els.linkStateLabel.textContent = "Offline";
  renderChat([]);
}

function handleApiError(error) {
  const message = error.message || "Request failed.";
  if (message.includes("Room not found or expired")) {
    state.room = null;
    state.roomCode = "";
    els.roomCodeInput.value = "";
    els.acceptUndoBtn.classList.add("hidden");
    els.rejectUndoBtn.classList.add("hidden");
    if (state.screen === "game" && state.mode === "room") {
      showScreen("online-setup");
      setSetupStatus(message);
    }
    updateInfo();
  }
  if (state.screen === "online-setup") {
    setSetupStatus(message);
  } else {
    setStatus(message);
  }
}

async function leaveRoom({ silent = false } = {}) {
  stopVoiceUi();
  if (!state.roomCode || state.leavingRoom) return;
  state.leavingRoom = true;
  const code = state.roomCode;
  try {
    await api("/api/rooms/leave", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
  } catch (error) {
    if (!silent) {
      handleApiError(error);
    }
  } finally {
    state.room = null;
    state.roomCode = "";
    els.roomCodeInput.value = "";
    els.acceptUndoBtn.classList.add("hidden");
    els.rejectUndoBtn.classList.add("hidden");
    state.leavingRoom = false;
  }
}

function leaveRoomOnUnload() {
  stopVoiceUi();
  if (!state.roomCode) return;
  const payload = JSON.stringify({ code: state.roomCode });
  const blob = new Blob([payload], { type: "application/json" });
  navigator.sendBeacon("/api/rooms/leave", blob);
}

async function goToLanding() {
  stopVoiceUi();
  if (state.roomCode) {
    await leaveRoom({ silent: true });
  }
  state.mode = "local";
  state.room = null;
  state.roomCode = "";
  showScreen("landing");
  setSetupStatus("Create a room or join one with a room code.");
}

async function enterLocalMode() {
  showScreen("game");
  state.mode = "local";
  await startLocal();
}

function enterOnlineSetup() {
  state.mode = "room";
  showScreen("online-setup");
  setSetupStatus("Create a room or join one with a room code.");
}

async function startLocal() {
  if (state.roomCode) {
    await leaveRoom({ silent: true });
  }
  const data = await api("/api/local/new", {
    method: "POST",
    body: JSON.stringify({ depth: Number(els.depthSelect.value) }),
  });
  state.mode = "local";
  state.local = data.state;
  state.room = null;
  state.roomCode = "";
  showScreen("game");
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
  if (state.roomCode) {
    await leaveRoom({ silent: true });
  }
  const name = els.playerNameInput.value.trim() || "Host";
  const turnLimitSeconds = Number(els.turnLimitSelect.value || 30);
  const data = await api("/api/rooms/create", {
    method: "POST",
    body: JSON.stringify({ name, turn_limit_seconds: turnLimitSeconds }),
  });
  state.mode = "room";
  state.room = data.room;
  state.roomCode = data.room.code;
  els.roomCodeInput.value = data.room.code;
  showScreen("game");
  setStatus(`Room created: ${data.room.code}`);
  updateInfo();
}

async function joinRoom() {
  if (state.roomCode) {
    await leaveRoom({ silent: true });
  }
  const code = els.roomCodeInput.value.trim().toUpperCase();
  const name = els.playerNameInput.value.trim() || "Player";
  const data = await api("/api/rooms/join", {
    method: "POST",
    body: JSON.stringify({ code, name }),
  });
  state.mode = "room";
  state.room = data.room;
  state.roomCode = data.room.code;
  showScreen("game");
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

async function requestRoomHint() {
  if (!state.roomCode) {
    return setStatus("Join or create a room first.");
  }
  const data = await api("/api/rooms/hint", {
    method: "POST",
    body: JSON.stringify({ code: state.roomCode }),
  });
  state.room = data.room;
  const moveText = state.room.active_hint && state.room.active_hint.move
    ? formatMove(state.room.active_hint.move)
    : "None";
  setStatus(`AI hint ready: ${moveText}`);
  updateInfo();
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

async function refresh() {
  try {
    if (state.screen !== "game") {
      return;
    }
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
  if (state.screen !== "game") return;
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
  if (state.screen !== "game") return;
  const rect = els.board.getBoundingClientRect();
  const scaleX = els.board.width / rect.width;
  const scaleY = els.board.height / rect.height;
  state.hoverPoint = fromCanvas((event.clientX - rect.left) * scaleX, (event.clientY - rect.top) * scaleY);
  if (state.mode === "local" && state.local) {
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null, null);
    return;
  }
  if (state.mode === "room" && state.room) {
    const suggestedMove = state.room.active_hint ? state.room.active_hint.move : null;
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null, suggestedMove);
    return;
  }
});

els.board.addEventListener("mouseleave", () => {
  state.hoverPoint = null;
  if (state.mode === "local" && state.local) {
    drawBoard(state.local.board, state.local.current_turn === "black" ? state.local.last_opponent_move : null, null);
    return;
  }
  if (state.mode === "room" && state.room) {
    const suggestedMove = state.room.active_hint ? state.room.active_hint.move : null;
    drawBoard(state.room.board, state.room.your_turn ? state.room.opponent_last_move : null, suggestedMove);
  }
});

els.goLocalBtn.addEventListener("click", () => enterLocalMode().catch(handleApiError));
els.goOnlineBtn.addEventListener("click", enterOnlineSetup);
els.backToHomeFromSetupBtn.addEventListener("click", () => goToLanding().catch(handleApiError));
els.backHomeBtn.addEventListener("click", () => goToLanding().catch(handleApiError));
els.startLocalBtn.addEventListener("click", () => startLocal().catch(handleApiError));
els.undoLocalBtn.addEventListener("click", () => localUndo().catch(handleApiError));
els.createRoomBtn.addEventListener("click", () => createRoom().catch(handleApiError));
els.joinRoomBtn.addEventListener("click", () => joinRoom().catch(handleApiError));
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

window.addEventListener("pagehide", leaveRoomOnUnload);

els.copyRoomBtn.addEventListener("click", async () => {
  if (!state.roomCode && !els.roomCodeInput.value.trim()) {
    return state.screen === "online-setup"
      ? setSetupStatus("No room code available.")
      : setStatus("No room code available.");
  }
  const code = state.roomCode || els.roomCodeInput.value.trim().toUpperCase();
  await navigator.clipboard.writeText(code);
  if (state.screen === "online-setup") {
    setSetupStatus(`Room code copied: ${code}`);
  } else {
    setStatus(`Room code copied: ${code}`);
  }
});

showScreen("landing");
syncPanels();
ensureVoiceControls();
drawBoard(Array.from({ length: SIZE }, () => Array(SIZE).fill(0)), null);
setInterval(refresh, POLL_MS);
