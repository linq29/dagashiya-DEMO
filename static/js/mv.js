(() => {
  const noren = document.querySelector(".wave-noren");
  const visual = document.querySelector(".main-visual");
  if (!noren || !visual) return;

  let ticking = false;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  const updateNoren = () => {
    const start = visual.offsetTop;
    const distance = Math.max(window.innerHeight * 0.9, 420);
    const progress = clamp((window.scrollY - start) / distance, 0, 1);

    const translateY = -progress * 220;
    const scale = 1 + progress * 0.55;

    noren.style.transform = `translate3d(0, ${translateY}px, 0) scale(${scale})`;
    ticking = false;
  };

  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(updateNoren);
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  updateNoren();
})();
