/* ==========================================================
   1. ハンバーガーメニュー
   ----------------------------------------------------------
   メニューボタンを押すとドロップダウンが開閉する。
   画面のどこかをクリックすると閉じる。
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

  const menuBtn = document.getElementById("menuBtn");
  const dropdown = document.getElementById("dropdownMenu");

  if (!menuBtn || !dropdown) return;

  // メニューボタンをクリック
  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation(); // 外側クリックで即時に閉じないようにする
    dropdown.classList.toggle("is-open");
  });

  // ドロップダウン内部クリックでは閉じない
  dropdown.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  // 画面の空白クリックで閉じる
  document.addEventListener("click", () => {
    dropdown.classList.remove("is-open");
  });

});


/* ==========================================================
   2. 無限カルーセル（50vw × 3枚 × 2セット）
   ----------------------------------------------------------
   ・CSS の animation を使って横にスライド
   ・バナー上にマウスを乗せるとスライドが一時停止
========================================================== */

const track = document.querySelector(".banner-track");
const area = document.querySelector(".banner-area");

if (track && area) {
  area.addEventListener("mouseenter", () => {
    track.style.animationPlayState = "paused";
  });
  area.addEventListener("mouseleave", () => {
    track.style.animationPlayState = "running";
  });
}


/* ==========================================================
   ※ 注意：
   このカルーセルは CSS の keyframes（slide）で
   アニメーションしているため、
   JavaScript 側では速度や遷移を直接制御していない。

   速度を変更したい場合は style.css 内の:

      animation: slide 20s linear infinite;

   の "20s" を変更すること。
========================================================== */

/* ==========================================================
   3. 検索候補の自動表示
   ----------------------------------------------------------
   検索ボックスに入力した文字列に応じて
   検索候補を自動表示する。
========================================================== */
document.addEventListener("DOMContentLoaded", () => {

  const keywordInput = document.getElementById("keyword");
  const searchBtn = document.getElementById("searchBtn");

  const list = document.getElementById("productList");
  
  if (!list) return;

  if (keywordInput) {
    keywordInput.addEventListener("input", search);
  }

  if (searchBtn) {
    searchBtn.addEventListener("click", search);
  }

  function search() {
    const keyword = keywordInput.value;

    fetch(`/api/search?keyword=${encodeURIComponent(keyword)}`)
      .then(res => res.json())
      .then(products => {
        const list = document.getElementById("productList");
        list.innerHTML = "";

        if (products.length === 0) {
          list.innerHTML = "<p>商品が見つかりません</p>";
          return;
        }

        products.forEach(product => {
          list.innerHTML += `
            <div class="product">
              <h3>${product.name}</h3>
              <p>価格: ${product.price}円</p>
            </div>
          `;
        });
      });
  }
});

/* ==========================================================
   4. 数量ステッパー（在庫上限チェック付き）
========================================================== */
document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll(".quantity-form");

  forms.forEach((form) => {
    const stepper = form.querySelector(".quantity-stepper");
    const input = form.querySelector(".quantity-input");
    const decreaseBtn = form.querySelector("[data-step='decrease']");
    const increaseBtn = form.querySelector("[data-step='increase']");
    const submitBtn = form.querySelector("button[type='submit']");
    const feedback = form.querySelector(".quantity-feedback");

    if (!stepper || !input) return;

    const min = Number(stepper.dataset.min || input.min || 1);
    const max = Number(stepper.dataset.max || input.max || 9999);

    const setFeedback = (message) => {
      if (!feedback) return;
      feedback.textContent = message;
    };

    const sync = () => {
      let value = Number(input.value);
      if (!Number.isFinite(value)) value = min;

      if (max < min) {
        input.value = 0;
        input.disabled = true;
        if (decreaseBtn) decreaseBtn.disabled = true;
        if (increaseBtn) increaseBtn.disabled = true;
        if (submitBtn) submitBtn.disabled = true;
        setFeedback("在庫切れです。");
        return;
      }

      if (value < min) value = min;
      if (value > max) value = max;
      input.value = value;

      if (decreaseBtn) decreaseBtn.disabled = value <= min;
      if (increaseBtn) increaseBtn.disabled = value >= max;
      if (submitBtn) submitBtn.disabled = false;
      setFeedback("");
    };

    if (decreaseBtn) {
      decreaseBtn.addEventListener("click", () => {
        const current = Number(input.value) || min;
        input.value = Math.max(min, current - 1);
        sync();
      });
    }

    if (increaseBtn) {
      increaseBtn.addEventListener("click", () => {
        const current = Number(input.value) || min;
        input.value = Math.min(max, current + 1);
        sync();
      });
    }

    input.addEventListener("input", () => {
      const current = Number(input.value);
      if (!Number.isFinite(current)) {
        if (submitBtn) submitBtn.disabled = true;
        setFeedback("数量を入力してください。");
        return;
      }
      if (current > max) {
        input.value = max;
        setFeedback(`在庫は最大 ${max} 個です。`);
      }
      sync();
    });

    input.addEventListener("blur", sync);
    sync();
  });
});

/* ==========================================================
   5. セクションの下からの出現アニメーション
   ----------------------------------------------------------
   ・main 内の section を対象
   ・section の最初の子 div があればそれを優先
   ・なければ section 自体に適用
========================================================== */
document.addEventListener("DOMContentLoaded", () => {
  const sections = document.querySelectorAll("main section");
  const targets = new Set();

  sections.forEach((section) => {
    const firstChild = section.firstElementChild;
    const firstChildDiv =
      firstChild && firstChild.tagName === "DIV" ? firstChild : null;
    targets.add(firstChildDiv || section);
  });

  // information 配下ページの info-card は個別にも必ず対象にする
  const infoCards = document.querySelectorAll("main .info-page .info-card");
  infoCards.forEach((card) => targets.add(card));

  const revealTargets = Array.from(targets);
  if (revealTargets.length === 0) return;

  revealTargets.forEach((target) => {
    target.classList.add("enter-up-on-view");
  });

  if (!("IntersectionObserver" in window)) {
    revealTargets.forEach((target) => target.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle("is-visible", entry.isIntersecting);
      });
    },
    {
      root: null,
      threshold: 0.01,
      rootMargin: "0px 0px -8% 0px",
    }
  );

  revealTargets.forEach((target) => observer.observe(target));
});
