// Shared UI: preferences, decrypt reveals, live refresh and the sync pill. No dependencies.
const root = document.documentElement;
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function pref(name, attr) {
  try { if (localStorage.getItem(name) === "1") root.setAttribute(attr, ""); } catch { /* storage off */ }
  document.querySelectorAll(`[data-toggle="${attr}"]`).forEach((btn) => {
    btn.setAttribute("aria-pressed", root.hasAttribute(attr) ? "true" : "false");
    btn.addEventListener("click", () => {
      const on = !root.hasAttribute(attr);
      root.toggleAttribute(attr, on);
      btn.setAttribute("aria-pressed", String(on));
      try { localStorage.setItem(name, on ? "1" : "0"); } catch { /* storage off */ }
    });
  });
}
pref("vt_large", "data-large-text");
pref("vt_lowpower", "data-low-power");

// Decrypt: characters scramble then lock in. Screen readers get only the final value.
const GLYPHS = "0123456789ABCDEF#%&@$";
export function decrypt(el, { duration } = {}) {
  const final = el.dataset.final ?? el.textContent;
  el.dataset.final = final;
  el.setAttribute("aria-label", final.trim());
  if (reduce || root.hasAttribute("data-low-power")) { el.textContent = final; return Promise.resolve(); }
  const dur = duration ?? Math.min(1600, 450 + final.length * 22);
  const start = performance.now();
  return new Promise((resolve) => {
    (function frame(now) {
      const p = Math.min(1, (now - start) / dur);
      const lock = Math.floor(p * final.length);
      el.textContent = [...final].map((c, i) => (i < lock || c === " " || c === "\n" ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join("");
      if (p < 1) requestAnimationFrame(frame); else { el.textContent = final; resolve(); }
    })(start);
  });
}
window.vtDecrypt = decrypt;
const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  entries.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target); decrypt(e.target); } });
}) : null;
document.querySelectorAll("[data-decrypt]").forEach((el) => {
  if (el.children.length) return; // only plain-text elements
  io ? io.observe(el) : decrypt(el);
});

// Live pages: poll a small JSON endpoint and refresh when something material changed.
document.querySelectorAll("[data-live-url]").forEach((el) => {
  const url = el.dataset.liveUrl, path = el.dataset.liveKey.split(".");
  const pick = (o) => path.reduce((v, k) => (v == null ? v : v[k]), o);
  let current = String(el.dataset.liveValue ?? "");
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (!r.ok) return;
      const v = String(pick(await r.json()) ?? "");
      if (v !== current) {
        current = v;
        const t = document.createElement("div");
        t.className = "live-toast"; t.setAttribute("role", "status"); t.textContent = "UPDATED JUST NOW";
        document.body.append(t);
        setTimeout(() => location.reload(), 700);
      }
    } catch { /* offline: try again later */ }
  }, 5000);
});

// Sync pill: honest about offline, things waiting on this phone, and work in progress.
async function localWaiting() {
  if (!("indexedDB" in window)) return 0;
  return new Promise((resolve) => {
    const req = indexedDB.open("votetrail", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("uploads", { keyPath: "key" });
    req.onerror = () => resolve(0);
    req.onsuccess = () => {
      try {
        const all = req.result.transaction("uploads", "readonly").objectStore("uploads").getAll();
        all.onsuccess = () => resolve((all.result || []).filter((i) => i.state === "saved" || i.state === "uploading").length);
        all.onerror = () => resolve(0);
      } catch { resolve(0); }
    };
  });
}
const pill = document.getElementById("sync");
async function refreshSync() {
  if (!pill) return;
  const waiting = await localWaiting();
  let processing = 0;
  if (navigator.onLine) {
    try { processing = (await (await fetch(pill.dataset.syncUrl, { credentials: "same-origin" })).json()).processing || 0; } catch { /* offline */ }
  }
  const text = document.getElementById("sync-text");
  pill.classList.remove("off", "busy");
  if (!navigator.onLine) { pill.classList.add("off"); text.textContent = waiting ? `OFFLINE · ${waiting} WAITING` : "OFFLINE"; }
  else if (waiting) { pill.classList.add("busy"); text.textContent = `SENDING ${waiting}`; }
  else if (processing) { pill.classList.add("busy"); text.textContent = `CHECKING ${processing}`; }
  else text.textContent = "SYNCED";
}
window.vtRefreshSync = refreshSync;
window.addEventListener("online", refreshSync);
window.addEventListener("offline", refreshSync);
refreshSync();
setInterval(refreshSync, 6000);

// Header: solid once the page scrolls.
const hdr = document.querySelector(".hdr");
if (hdr && !hdr.classList.contains("solid")) {
  const onScroll = () => hdr.classList.toggle("scrolled", window.scrollY > 20);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

// Headlines reveal word by word; blocks fade up as they enter the screen.
function split(el) {
  let i = 0;
  const walk = (node) => {
    [...node.childNodes].forEach((n) => {
      if (n.nodeType === 3) {
        const frag = document.createDocumentFragment();
        n.textContent.split(/(\s+)/).forEach((part) => {
          if (!part) return;
          if (/^\s+$/.test(part)) { frag.append(document.createTextNode(part)); return; }
          const s = document.createElement("span");
          s.className = "w";
          s.textContent = part;
          s.style.transitionDelay = `${i++ * 70}ms`;
          frag.append(s);
        });
        n.replaceWith(frag);
      } else if (n.nodeType === 1) walk(n);
    });
  };
  walk(el);
}
document.querySelectorAll("[data-split]").forEach(split);
const revealIo = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    revealIo.unobserve(e.target);
    e.target.classList.add("in");
    e.target.dispatchEvent(new CustomEvent("reveal"));
  });
}, { threshold: 0.2 }) : null;
document.querySelectorAll("[data-split],[data-reveal]").forEach((el) => (revealIo ? revealIo.observe(el) : el.classList.add("in")));

// Journey timeline: grow the progress line once the page has painted.
document.querySelectorAll(".timeline .prog[data-width]").forEach((bar) => {
  requestAnimationFrame(() => setTimeout(() => (bar.style.width = `${bar.dataset.width}%`), 120));
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
