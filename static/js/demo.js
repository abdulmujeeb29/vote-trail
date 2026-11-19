// Demo replay: plays saved scenes on a timer. No network calls except static files.
const scenes = [...document.querySelectorAll(".scene")];
if (scenes.length) {
  const bars = [...document.querySelectorAll("#rail b")];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let idx = 0, playing = false, elapsed = 0, last = 0, timers = [];
  const total = scenes.reduce((n, s) => n + Number(s.dataset.dur), 0);
  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const later = (ms, fn) => timers.push(setTimeout(fn, reduce ? 0 : ms));

  function scramble(el, final, ms = 1200) {
    el.setAttribute("aria-label", final);
    if (reduce) { el.textContent = final; return; }
    const t0 = performance.now();
    (function f(now) {
      const p = Math.min(1, (now - t0) / ms), lock = Math.floor(p * final.length);
      el.textContent = [...final].map((c, i) => (i < lock ? c : "0123456789#%"[(Math.random() * 12) | 0])).join("");
      if (p < 1) requestAnimationFrame(f); else el.textContent = final;
    })(t0);
  }

  const enter = {
    2: () => {
      const data = JSON.parse(document.getElementById("ussd-data").textContent);
      const screen = document.getElementById("ussd-screen"), key = document.getElementById("ussd-key");
      data.forEach((s, i) => later(i * 3000, () => { key.textContent = `› ${s.input}`; screen.textContent = s.screen.slice(4); }));
    },
    4: () => {
      const irev = JSON.parse(document.getElementById("irev-data").textContent);
      document.querySelectorAll("tr[data-party]").forEach((row, i) => {
        const wall = row.children[1], cell = row.children[2], p = row.dataset.party;
        later(800 + i * 500, () => scramble(wall, wall.dataset.final ?? (wall.dataset.final = wall.textContent)));
        later(3500 + i * 600, () => {
          scramble(cell, String(irev[p] ?? "—"));
          if (String(irev[p]) !== wall.dataset.final) later(1300, () => row.classList.add("diff"));
        });
      });
      later(9000, () => { document.getElementById("result-card").hidden = false; });
    },
    5: () => {
      const n = Number(document.getElementById("rumour-forwards").textContent), out = document.getElementById("fwd");
      for (let i = 1; i <= n; i++) later(i * 90, () => { out.textContent = i; });
      later(n * 90 + 1500, () => {
        scramble(document.getElementById("rumour-head"), document.getElementById("rumour-final").textContent, 1400);
        later(1600, () => { document.getElementById("rumour-body").hidden = false; });
      });
    },
  };

  function show(i) {
    timers.forEach(clearTimeout); timers = [];
    idx = Math.max(0, Math.min(scenes.length - 1, i));
    scenes.forEach((s, j) => s.classList.toggle("on", j === idx));
    elapsed = scenes.slice(0, idx).reduce((n, s) => n + Number(s.dataset.dur), 0);
    document.getElementById("result-card")?.setAttribute("hidden", "");
    document.getElementById("rumour-body")?.setAttribute("hidden", "");
    document.querySelectorAll("tr.diff").forEach((r) => r.classList.remove("diff"));
    enter[idx]?.();
    paint();
  }

  function paint() {
    let acc = 0;
    scenes.forEach((s, j) => {
      const d = Number(s.dataset.dur);
      bars[j].style.width = `${Math.max(0, Math.min(1, (elapsed - acc) / d)) * 100}%`;
      acc += d;
    });
    document.getElementById("clock").textContent = fmt(elapsed);
  }

  function tick(now) {
    if (!playing) return;
    elapsed += (now - last) / 1000; last = now;
    const end = scenes.slice(0, idx + 1).reduce((n, s) => n + Number(s.dataset.dur), 0);
    if (elapsed >= end) {
      if (idx === scenes.length - 1) { playing = false; document.getElementById("play").textContent = "Play"; window.__demoDone = true; paint(); return; }
      const keep = elapsed; show(idx + 1); elapsed = keep;
    }
    paint();
    requestAnimationFrame(tick);
  }

  const play = document.getElementById("play");
  play.addEventListener("click", () => {
    playing = !playing; play.textContent = playing ? "Pause" : "Play";
    if (playing) { if (window.__demoDone) { window.__demoDone = false; show(0); } last = performance.now(); requestAnimationFrame(tick); }
  });
  document.getElementById("next").addEventListener("click", () => show(idx + 1));
  document.getElementById("prev").addEventListener("click", () => show(idx - 1));
  document.getElementById("restart").addEventListener("click", () => { window.__demoDone = false; show(0); });
  window.__demoTotal = total;
  window.__demoSpeed = (x) => { const orig = scenes.map((s) => s.dataset.dur); scenes.forEach((s, j) => { s.dataset.dur = orig[j] / x; }); };
  show(0);
}
