document.addEventListener("DOMContentLoaded", () => {
    const startBtn = document.getElementById("gachaStart");
    const coin = document.querySelector(".coin");

    const modal = document.getElementById("gachaModal");
    const capsuleImg = document.getElementById("capsuleImg");
    const resultText = document.getElementById("resultText");
    const closeModal = document.getElementById("closeModal");
    const backdrop = modal?.querySelector(".modal__backdrop");
    const confirmModal = document.getElementById("gachaConfirmModal");
    const confirmBackdrop = confirmModal?.querySelector(".modal__backdrop");
    const confirmOkBtn = document.getElementById("gachaConfirmOk");
    const confirmCancelBtn = document.getElementById("gachaConfirmCancel");
    const noticeModal = document.getElementById("gachaNoticeModal");
    const noticeBackdrop = noticeModal?.querySelector(".modal__backdrop");
    const noticeOkBtn = document.getElementById("gachaNoticeOk");
    const noticeText = document.getElementById("gachaNoticeText");

    // HTMLのdata属性から画像のパスを取得
    const assetsEl = document.getElementById("gacha-assets");
    const capsuleGold = assetsEl?.dataset.capsuleGold; // 10%
    const capsuleBlue = assetsEl?.dataset.capsuleBlue; // 5%
    const capsuleRed = assetsEl?.dataset.capsuleRed;   // ハズレ

    const items = ["10%引き券", "5%引き券", "ハズレ"];
    const weights = [0.1, 0.2, 0.7]; // 当選確率の設定

    let spinning = false;

    // ---------- ヘルパー関数 ----------

    // 重み付き抽選ロジック
    function pickWeighted() {
        const r = Math.random();
        let sum = 0;
        for (let i = 0; i < items.length; i++) {
            sum += weights[i];
            if (r < sum) return items[i];
        }
        return items[items.length - 1];
    }

    // 結果に応じた画像と文字色を返す
    function uiByResult(result) {
        if (result === "10%引き券") {
            return { src: capsuleGold, color: "#D4AF37" }; // 金色系
        }
        if (result === "5%引き券") {
            return { src: capsuleBlue, color: "#2F6FED" }; // 青色系
        }
        return { src: capsuleRed, color: "#E74C3C" };   // 赤色系
    }

    // 指定時間待機するプロミス
    function wait(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    // アニメーション終了を待機するプロミス
    function waitAnimationEnd(el) {
        return new Promise((resolve) => {
            const onEnd = () => {
                el.removeEventListener("animationend", onEnd);
                resolve();
            };
            el.addEventListener("animationend", onEnd);
        });
    }

    // 画像のプリロード
    [capsuleGold, capsuleBlue, capsuleRed].filter(Boolean).forEach((src) => {
        const img = new Image();
        img.src = src;
    });

    // モーダルを表示（画像ロード完了後にアニメーションを開始するのがコツ）
    function openModal(result) {
        const { src, color } = uiByResult(result);

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");

        resultText.textContent = `結果：${result}`;
        resultText.style.color = color;

        // アニメーション状態をリセット（連続で引いた際の再発火用）
        capsuleImg.classList.remove("is-pop");
        capsuleImg.style.opacity = "0";
        capsuleImg.style.transform = "scale(0.2)";

        // 画像の読み込みが完了してからアニメーションを開始
        capsuleImg.onload = () => {
            void capsuleImg.offsetWidth; // 強制リフロー（再描画）
            capsuleImg.classList.add("is-pop");
        };

        capsuleImg.src = src || "";
    }

    // モーダルを閉じる
    function close() {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
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

    // ---------- イベントリスナー ----------
    startBtn?.addEventListener("click", async () => {
        if (spinning) return;

        const confirmed = await confirmConsumeTicket();
        if (!confirmed) return;

        // 🔽 まずサーバーで回数チェック＆消費
        const res = await fetch("/gacha/use", { method: "POST" });
        const data = await res.json();

        if (!data.ok) {
            showNotice(data.message || "わくわく券がありません");
            return;
        }
        decrementHeaderGachaCount();

        spinning = true;
        startBtn.disabled = true;

        // 🔽 ここで初めて結果を決める
        const result = pickWeighted();

        // コイン投入アニメーション
        if (coin) {
            coin.classList.remove("is-animating");
            void coin.offsetWidth;
            coin.classList.add("is-animating");
            await waitAnimationEnd(coin);
        } else {
            await wait(500);
        }

        // 引き券送信
        if (result === "10%引き券" || result === "5%引き券") {
            fetch("/apply_discount", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ coupon: result }),
            }).catch(() => {});
        }

        await wait(1000);
        openModal(result);

        spinning = false;
        startBtn.disabled = false;
    });

    closeModal?.addEventListener("click", close);
    backdrop?.addEventListener("click", close);
    noticeOkBtn?.addEventListener("click", () => closeSimpleModal(noticeModal));
    noticeBackdrop?.addEventListener("click", () => closeSimpleModal(noticeModal));
});
