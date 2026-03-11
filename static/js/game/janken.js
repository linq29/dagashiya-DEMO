console.log("janken.js loaded");

document.addEventListener("DOMContentLoaded", () => {

    // =========================
    // 状態管理
    // =========================
    const gameState = {
        round: 0,               // 現在の回戦（1〜3）
        playerWins: 0,
        computerWins: 0,
        setStarted: false,
        isPlaying: false
    };

    // =========================
    // 要素取得
    // =========================
    const choiceButtons = document.querySelectorAll(".choice-btn");
    const playerScoreEl = document.getElementById("player-score");
    const computerScoreEl = document.getElementById("computer-score");
    const gameStatusEl = document.getElementById("game-status");
    const jankenResultEl = document.getElementById("janken-result");
    const playerHandEl = document.getElementById("player-hand");
    const computerHandEl = document.getElementById("computer-hand");
    const resultMessageEl = document.getElementById("result-message");
    const roundRestartWrap = document.getElementById("janken-restart");
    const roundRestartBtn = document.getElementById("round-restart-btn");
    const confirmModal = document.getElementById("jankenConfirmModal");
    const confirmBackdrop = confirmModal?.querySelector(".modal__backdrop");
    const confirmOkBtn = document.getElementById("jankenConfirmOk");
    const confirmCancelBtn = document.getElementById("jankenConfirmCancel");
    const noticeModal = document.getElementById("jankenNoticeModal");
    const noticeBackdrop = noticeModal?.querySelector(".modal__backdrop");
    const noticeText = document.getElementById("jankenNoticeText");
    const noticeOkBtn = document.getElementById("jankenNoticeOk");

    // =========================
    // サウンド
    // =========================
    const sfxWin = document.getElementById("sfx-win");
    const sfxLose = document.getElementById("sfx-lose");
    const sfxDraw = document.getElementById("sfx-draw");

    // =========================
    // 定数
    // =========================
    const handEmojis = {
        rock: "✊",
        scissors: "✌️",
        paper: "✋"
    };

    const handNames = {
        rock: "グー",
        scissors: "チョキ",
        paper: "パー"
    };

    // =========================
    // イベント登録
    // =========================
    choiceButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            playRound(btn.dataset.choice);
        });
    });

    roundRestartBtn?.addEventListener("click", resetGame);

    // =========================
    // メイン処理
    // =========================
    async function playRound(playerChoice) {
        if (gameState.isPlaying) return;

        // 🔽 1回戦目開始時のみわくわく券を消費
        if (!gameState.setStarted) {
            const confirmed = await confirmConsumeTicket();
            if (!confirmed) return;

            const res = await fetch("/gacha/use", { method: "POST" });
            const data = await res.json();

            if (!data.ok) {
                showNotice(data.message || "わくわく券がありません");
                return;
            }
            decrementHeaderGachaCount();

            gameState.setStarted = true;
            gameState.round = 1;
            gameState.playerWins = 0;
            gameState.computerWins = 0;
        } else {
            gameState.round++;
        }

        gameState.isPlaying = true;
        disableButtons(true);

        const computerChoice = getComputerChoice();

        // 表示
        playerHandEl.textContent = handEmojis[playerChoice];
        computerHandEl.textContent = handEmojis[computerChoice];

        const result = judge(playerChoice, computerChoice);

        // 勝敗カウント
        if (result === "win") gameState.playerWins++;
        if (result === "lose") gameState.computerWins++;

        updateScore();
        showRoundResult(result, playerChoice, computerChoice);

        playSound(result);

        // 結果表示
        jankenResultEl.style.display = "block";

        // 3回戦終了チェック
        if (gameState.round === 3) {
            setTimeout(endSet, 800);
        } else {
            gameState.isPlaying = false;
            disableButtons(false);
        }
    }

    // =========================
    // 勝敗判定
    // =========================
    function judge(player, computer) {
        if (player === computer) return "draw";

        if (
            (player === "rock" && computer === "scissors") ||
            (player === "scissors" && computer === "paper") ||
            (player === "paper" && computer === "rock")
        ) {
            return "win";
        }
        return "lose";
    }

    // =========================
    // コンピューター選択
    // =========================
    function getComputerChoice() {
        const hands = ["rock", "scissors", "paper"];
        return hands[Math.floor(Math.random() * 3)];
    }

    // =========================
    // スコア更新
    // =========================
    function updateScore() {
        playerScoreEl.textContent = gameState.playerWins;
        computerScoreEl.textContent = gameState.computerWins;
    }

    // =========================
    // ラウンド結果表示
    // =========================
    function showRoundResult(result, player, computer) {
        let msg = `第${gameState.round}回戦：`;

        if (result === "win") msg += "あなたの勝ち！";
        if (result === "lose") msg += "コンピューターの勝ち";
        if (result === "draw") msg += "あいこ";

        gameStatusEl.textContent =
            `${msg}（${handNames[player]} vs ${handNames[computer]}）`;

        resultMessageEl.textContent = msg;
        resultMessageEl.className = `result-message ${result}`;
    }

    // =========================
    // セット終了処理
    // =========================
    async function endSet() {
        disableButtons(true);

        let finalMessage = "";

        if (gameState.playerWins > gameState.computerWins) {
            finalMessage = "🎉 あなたの勝利！10％引き券を獲得！";

            await fetch("/apply_discount", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ coupon: "10%引き券" })
            });

        } else if (gameState.playerWins < gameState.computerWins) {
            finalMessage = "残念…コンピューターの勝ち";
        } else {
            finalMessage = "引き分け！今回は報酬なし";
        }

        resultMessageEl.textContent = finalMessage;
        gameStatusEl.textContent = finalMessage;
        roundRestartWrap.style.display = "flex";
    }

    // =========================
    // リセット
    // =========================
    function resetGame() {
        gameState.round = 0;
        gameState.playerWins = 0;
        gameState.computerWins = 0;
        gameState.setStarted = false;
        gameState.isPlaying = false;

        playerScoreEl.textContent = 0;
        computerScoreEl.textContent = 0;
        gameStatusEl.textContent = "コンピューターに勝ってポイントを獲得しよう！";

        jankenResultEl.style.display = "none";
        roundRestartWrap.style.display = "none";
        disableButtons(false);
    }

    // =========================
    // ボタン制御
    // =========================
    function disableButtons(flag) {
        choiceButtons.forEach(btn => btn.disabled = flag);
    }

    function openSimpleModal(targetModal) {
        targetModal?.classList.add("is-open");
        targetModal?.setAttribute("aria-hidden", "false");
    }

    function closeSimpleModal(targetModal) {
        targetModal?.classList.remove("is-open");
        targetModal?.setAttribute("aria-hidden", "true");
    }

    function confirmConsumeTicket() {
        return new Promise((resolve) => {
            openSimpleModal(confirmModal);

            const cleanup = () => {
                confirmOkBtn?.removeEventListener("click", onOk);
                confirmCancelBtn?.removeEventListener("click", onCancel);
                confirmBackdrop?.removeEventListener("click", onCancel);
                closeSimpleModal(confirmModal);
            };

            const onOk = () => {
                cleanup();
                resolve(true);
            };

            const onCancel = () => {
                cleanup();
                resolve(false);
            };

            confirmOkBtn?.addEventListener("click", onOk);
            confirmCancelBtn?.addEventListener("click", onCancel);
            confirmBackdrop?.addEventListener("click", onCancel);
        });
    }

    function showNotice(message) {
        noticeText.textContent = message;
        openSimpleModal(noticeModal);
    }

    function decrementHeaderGachaCount() {
        const countEl = document.getElementById("headerGachaCount");
        if (!countEl) return;
        const current = Number.parseInt(countEl.dataset.count || countEl.textContent || "0", 10);
        const next = Math.max(0, Number.isNaN(current) ? 0 : current - 1);
        countEl.dataset.count = String(next);
        countEl.textContent = String(next);
    }

    // =========================
    // サウンド
    // =========================
    function playSound(result) {
        [sfxWin, sfxLose, sfxDraw].forEach(s => {
            s.pause();
            s.currentTime = 0;
        });

        if (result === "win") sfxWin.play().catch(() => {});
        if (result === "lose") sfxLose.play().catch(() => {});
        if (result === "draw") sfxDraw.play().catch(() => {});
    }

    noticeOkBtn?.addEventListener("click", () => closeSimpleModal(noticeModal));
    noticeBackdrop?.addEventListener("click", () => closeSimpleModal(noticeModal));
});
