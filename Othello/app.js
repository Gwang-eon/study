const SIZE = 8;
const EMPTY = 0;
const BLACK = 1;
const WHITE = 2;

const boardEl = document.getElementById("board");
const blackCountEl = document.getElementById("black-count");
const whiteCountEl = document.getElementById("white-count");
const turnIndicatorEl = document.getElementById("turn-indicator");
const statusEl = document.getElementById("status");
const matchEl = document.getElementById("match");
const restartBtn = document.getElementById("restart");
const toggleHintsBtn = document.getElementById("toggle-hints");
const difficultySelect = document.getElementById("difficulty");
const depthSelect = document.getElementById("depth");
const tempoInput = document.getElementById("tempo");

let board = [];
let currentPlayer = BLACK;
let showHints = true;
let aiDifficulty = difficultySelect.value;
let aiThinking = false;
let HUMAN = BLACK;
let AI = WHITE;
let hardDepth = Number(depthSelect.value);
let lastMove = null;
let lastTurn = currentPlayer;
let audioCtx = null;
let audioReady = false;
let tempo = Number(tempoInput.value);

const directions = [
  [-1, -1],
  [-1, 0],
  [-1, 1],
  [0, -1],
  [0, 1],
  [1, -1],
  [1, 0],
  [1, 1],
];

const createBoard = () => {
  board = Array.from({ length: SIZE }, () => Array(SIZE).fill(EMPTY));
  const mid = SIZE / 2;
  board[mid - 1][mid - 1] = WHITE;
  board[mid][mid] = WHITE;
  board[mid - 1][mid] = BLACK;
  board[mid][mid - 1] = BLACK;
  currentPlayer = BLACK;
};

const inBounds = (row, col) => row >= 0 && row < SIZE && col >= 0 && col < SIZE;

const opponent = (player) => (player === BLACK ? WHITE : BLACK);

const getFlips = (row, col, player, boardState = board) => {
  if (boardState[row][col] !== EMPTY) return [];
  const flips = [];

  directions.forEach(([dr, dc]) => {
    let r = row + dr;
    let c = col + dc;
    const line = [];

    while (inBounds(r, c) && boardState[r][c] === opponent(player)) {
      line.push([r, c]);
      r += dr;
      c += dc;
    }

    if (line.length > 0 && inBounds(r, c) && boardState[r][c] === player) {
      flips.push(...line);
    }
  });

  return flips;
};

const getValidMoves = (player, boardState = board) => {
  const moves = [];

  for (let row = 0; row < SIZE; row += 1) {
    for (let col = 0; col < SIZE; col += 1) {
      if (boardState[row][col] !== EMPTY) continue;
      const flips = getFlips(row, col, player, boardState);
      if (flips.length > 0) {
        moves.push({ row, col, flips });
      }
    }
  }

  return moves;
};

const applyMove = (move, player = currentPlayer, boardState = board) => {
  boardState[move.row][move.col] = player;
  move.flips.forEach(([r, c]) => {
    boardState[r][c] = player;
  });
};

const counts = (boardState = board) => {
  let black = 0;
  let white = 0;

  boardState.flat().forEach((cell) => {
    if (cell === BLACK) black += 1;
    if (cell === WHITE) white += 1;
  });

  return { black, white };
};

const updateStats = () => {
  const { black, white } = counts();
  blackCountEl.textContent = black;
  whiteCountEl.textContent = white;
  turnIndicatorEl.textContent = currentPlayer === BLACK ? "흑" : "백";
};

const initAudio = () => {
  if (audioReady) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  audioReady = true;
};

const playTone = (frequency, duration, type = "sine", volume = 0.08) => {
  if (!audioReady || !audioCtx) return;
  const oscillator = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  oscillator.type = type;
  oscillator.frequency.value = frequency * (0.95 + tempo * 0.05);
  gain.gain.setValueAtTime(volume, audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
  oscillator.connect(gain);
  gain.connect(audioCtx.destination);
  oscillator.start();
  oscillator.stop(audioCtx.currentTime + duration);
};

const playMoveSound = () => playTone(440, 0.08, "triangle", 0.08);

const playFlipSound = (count) => {
  const base = count >= 5 ? 520 : 480;
  playTone(base, 0.06, "sine", 0.06);
  playTone(base + 120, 0.07, "sine", 0.04);
};

const playTurnSound = () => playTone(360, 0.07, "triangle", 0.05);

const playPassSound = () => playTone(280, 0.08, "sine", 0.04);

const flashCombo = (count) => {
  if (count < 3) return;
  const wrap = boardEl.parentElement;
  wrap.classList.add("combo");
  setTimeout(() => wrap.classList.remove("combo"), 220);
};

const shakeBoard = () => {
  const wrap = boardEl.parentElement;
  wrap.classList.remove("shake");
  void wrap.offsetWidth;
  wrap.classList.add("shake");
  const duration = Math.max(140, 240 / tempo);
  boardEl.style.animationDuration = `${duration}ms`;
  setTimeout(() => wrap.classList.remove("shake"), duration + 20);
};

const cloneBoard = (boardState) => boardState.map((row) => row.slice());

const positionalWeights = [
  [120, -20, 20, 5, 5, 20, -20, 120],
  [-20, -40, -5, -5, -5, -5, -40, -20],
  [20, -5, 15, 3, 3, 15, -5, 20],
  [5, -5, 3, 3, 3, 3, -5, 5],
  [5, -5, 3, 3, 3, 3, -5, 5],
  [20, -5, 15, 3, 3, 15, -5, 20],
  [-20, -40, -5, -5, -5, -5, -40, -20],
  [120, -20, 20, 5, 5, 20, -20, 120],
];

const evaluateBoard = (boardState, player) => {
  const { black, white } = counts(boardState);
  const playerCount = player === BLACK ? black : white;
  const opponentCount = player === BLACK ? white : black;

  let positional = 0;
  for (let row = 0; row < SIZE; row += 1) {
    for (let col = 0; col < SIZE; col += 1) {
      if (boardState[row][col] === player) positional += positionalWeights[row][col];
      if (boardState[row][col] === opponent(player)) positional -= positionalWeights[row][col];
    }
  }

  const mobility =
    getValidMoves(player, boardState).length - getValidMoves(opponent(player), boardState).length;
  const discDiff = playerCount - opponentCount;

  return positional + mobility * 4 + discDiff * 2;
};

const minimax = (boardState, depth, player, maximizing, alpha, beta) => {
  const moves = getValidMoves(player, boardState);
  if (depth === 0) {
    return evaluateBoard(boardState, AI);
  }

  if (moves.length === 0) {
    const opponentMoves = getValidMoves(opponent(player), boardState);
    if (opponentMoves.length === 0) {
      return evaluateBoard(boardState, AI);
    }
    return minimax(boardState, depth - 1, opponent(player), !maximizing, alpha, beta);
  }

  if (maximizing) {
    let best = -Infinity;
    moves.forEach((move) => {
      const nextBoard = cloneBoard(boardState);
      applyMove(move, player, nextBoard);
      const score = minimax(nextBoard, depth - 1, opponent(player), false, alpha, beta);
      best = Math.max(best, score);
      alpha = Math.max(alpha, score);
      if (beta <= alpha) return;
    });
    return best;
  }

  let best = Infinity;
  moves.forEach((move) => {
    const nextBoard = cloneBoard(boardState);
    applyMove(move, player, nextBoard);
    const score = minimax(nextBoard, depth - 1, opponent(player), true, alpha, beta);
    best = Math.min(best, score);
    beta = Math.min(beta, score);
    if (beta <= alpha) return;
  });
  return best;
};

const chooseAIMove = (validMoves) => {
  if (validMoves.length === 0) return null;

  if (aiDifficulty === "easy") {
    return validMoves[Math.floor(Math.random() * validMoves.length)];
  }

  if (aiDifficulty === "medium") {
    let bestMove = validMoves[0];
    let bestScore = -Infinity;

    validMoves.forEach((move) => {
      const nextBoard = cloneBoard(board);
      applyMove(move, AI, nextBoard);
      const opponentMoves = getValidMoves(HUMAN, nextBoard).length;
      const isCorner =
        (move.row === 0 && move.col === 0) ||
        (move.row === 0 && move.col === 7) ||
        (move.row === 7 && move.col === 0) ||
        (move.row === 7 && move.col === 7);
      const isEdge = move.row === 0 || move.row === 7 || move.col === 0 || move.col === 7;
      const score =
        move.flips.length * 2 + (isEdge ? 6 : 0) + (isCorner ? 80 : 0) - opponentMoves * 3;

      if (score > bestScore) {
        bestScore = score;
        bestMove = move;
      }
    });

    return bestMove;
  }

  let bestMove = validMoves[0];
  let bestScore = -Infinity;
  const depth = Math.max(2, Math.min(5, hardDepth));
  validMoves.forEach((move) => {
    const nextBoard = cloneBoard(board);
    applyMove(move, AI, nextBoard);
    const score = minimax(nextBoard, depth, HUMAN, false, -Infinity, Infinity);
    if (score > bestScore) {
      bestScore = score;
      bestMove = move;
    }
  });
  return bestMove;
};

const maybeAutoMove = () => {
  if (currentPlayer !== AI || aiThinking) return;
  const validMoves = getValidMoves(currentPlayer);
  if (validMoves.length === 0) return;

  aiThinking = true;
  boardEl.parentElement.classList.add("locked");
  statusEl.textContent = "AI가 생각 중입니다...";
  setTimeout(() => {
    const chosen = chooseAIMove(validMoves);
    if (chosen) {
      applyMove(chosen, AI);
      lastMove = { row: chosen.row, col: chosen.col, flips: chosen.flips };
      playMoveSound();
      playFlipSound(chosen.flips.length);
      flashCombo(chosen.flips.length);
      currentPlayer = opponent(currentPlayer);
    }
    aiThinking = false;
    boardEl.parentElement.classList.remove("locked");
    renderBoard();
  }, 350);
};

const renderBoard = () => {
  const validMoves = getValidMoves(currentPlayer);
  boardEl.innerHTML = "";

  for (let row = 0; row < SIZE; row += 1) {
    for (let col = 0; col < SIZE; col += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.setAttribute("role", "gridcell");
      cell.dataset.row = row;
      cell.dataset.col = col;
      if (lastMove && lastMove.row === row && lastMove.col === col) {
        cell.classList.add("last");
      }
      if (lastMove && lastMove.flips?.some(([r, c]) => r === row && c === col)) {
        cell.classList.add("flipped");
      }

      const value = board[row][col];
      if (value === BLACK || value === WHITE) {
        const disk = document.createElement("div");
        disk.className = `disk ${value === BLACK ? "black" : "white"}`;
        if (lastMove && lastMove.row === row && lastMove.col === col) {
          disk.classList.add("spawn");
          const spawnDuration = Math.max(160, 320 - lastMove.flips.length * 8);
          disk.style.setProperty("--spawn-duration", `${spawnDuration / tempo}ms`);
        }
        if (lastMove && lastMove.flips?.some(([r, c]) => r === row && c === col)) {
          disk.classList.add("flip");
          const index = lastMove.flips.findIndex(([r, c]) => r === row && c === col);
          const flipCount = Math.max(1, lastMove.flips.length);
          const speedBoost = Math.max(0, Math.min(4, flipCount - 3));
          const delayStep = Math.max(16, 38 - speedBoost * 4);
          const delay = Math.min(140, index * delayStep);
          const flipDuration = Math.max(220, 520 - speedBoost * 60);
          disk.style.animationDelay = `${delay / tempo}ms`;
          disk.style.setProperty("--flip-duration", `${flipDuration / tempo}ms`);
        }
        cell.appendChild(disk);
      }

      if (showHints && validMoves.some((move) => move.row === row && move.col === col)) {
        cell.classList.add("hint");
      }

      boardEl.appendChild(cell);
    }
  }

  updateStats();
  updateStatus(validMoves);
  if (currentPlayer !== lastTurn) {
    playTurnSound();
    lastTurn = currentPlayer;
  }
  maybeAutoMove();
};

const updateStatus = (validMoves) => {
  if (validMoves.length === 0) {
    const opponentMoves = getValidMoves(opponent(currentPlayer));
    if (opponentMoves.length === 0) {
      const { black, white } = counts();
      if (black === white) {
        statusEl.textContent = "무승부입니다. 다시 도전해볼까요?";
      } else if (black > white) {
        statusEl.textContent = "흑이 승리했습니다!";
      } else {
        statusEl.textContent = "백이 승리했습니다!";
      }
      return;
    }

    statusEl.textContent = "놓을 수 있는 칸이 없어 턴이 넘어갑니다.";
    currentPlayer = opponent(currentPlayer);
    playPassSound();
    setTimeout(renderBoard, 450);
    return;
  }

  const whose = currentPlayer === HUMAN ? "당신" : "AI";
  statusEl.textContent = `${whose}의 차례입니다.`;
};

const handleClick = (event) => {
  if (currentPlayer !== HUMAN || aiThinking) return;
  const cell = event.target.closest(".cell");
  if (!cell) return;

  const row = Number(cell.dataset.row);
  const col = Number(cell.dataset.col);
  const possibleMoves = getValidMoves(currentPlayer);
  const chosen = possibleMoves.find((move) => move.row === row && move.col === col);

  if (!chosen) return;

  applyMove(chosen);
  lastMove = { row, col, flips: chosen.flips };
  playMoveSound();
  playFlipSound(chosen.flips.length);
  flashCombo(chosen.flips.length);
  shakeBoard();
  currentPlayer = opponent(currentPlayer);
  renderBoard();
};

const restart = () => {
  const coin = Math.random() < 0.5;
  HUMAN = coin ? BLACK : WHITE;
  AI = opponent(HUMAN);
  matchEl.textContent = `당신: ${HUMAN === BLACK ? "흑" : "백"} · AI: ${
    AI === BLACK ? "흑" : "백"
  }`;
  createBoard();
  lastMove = null;
  lastTurn = currentPlayer;
  renderBoard();
};

const toggleHints = () => {
  showHints = !showHints;
  toggleHintsBtn.textContent = showHints ? "힌트 끄기" : "힌트 켜기";
  renderBoard();
};

difficultySelect.addEventListener("change", () => {
  aiDifficulty = difficultySelect.value;
  if (currentPlayer === AI) {
    renderBoard();
  }
});

depthSelect.addEventListener("change", () => {
  hardDepth = Number(depthSelect.value);
  if (currentPlayer === AI) {
    renderBoard();
  }
});

tempoInput.addEventListener("input", () => {
  tempo = Number(tempoInput.value);
});

boardEl.addEventListener("click", handleClick);
restartBtn.addEventListener("click", restart);
toggleHintsBtn.addEventListener("click", toggleHints);
window.addEventListener("pointerdown", initAudio, { once: true });

restart();
