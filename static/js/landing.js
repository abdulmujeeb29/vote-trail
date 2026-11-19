// Landing page: 3D ballot box hero, the scroll story (Amaka's demo), and the channel board.
import { box, el } from "./scene3d.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.hasAttribute("data-low-power");

// ---------- hero: ballot box with a result sheet dropping into the slot ----------
const heroIso = $("#hero-iso");
if (heroIso) {
  heroIso.append(el("floor"), el("floor-glow"), el("pulse-ring"));
  const ballot = box(240, 240, 190, {
    cls: "ballot",
    top: '<div class="slot"></div><div class="ballot-label">PU 37/06/02/004</div>',
    front: '<div class="ballot-front"><span><b>●</b> COUNTED · CHECKED</span><span>VOTETRAIL</span></div>',
  });
  ballot.append(el("paper", "EC8A · PB<i></i><i></i><div class='hand'>187</div><i></i>"));
  heroIso.append(ballot);
  const stage = heroIso.parentElement;
  stage.addEventListener("mousemove", (e) => {
    if (calm()) return;
    const r = stage.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    heroIso.style.setProperty("--rz", `${-45 + x * 18}deg`);
    heroIso.style.setProperty("--rx", `${58 - y * 10}deg`);
  });
}

// ---------- channel board: core chip + four channel chips, linked by traces ----------
const boardIso = $("#board-iso");
if (boardIso) {
  boardIso.append(el("floor"));
  const icons = {
    WEB: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8"/></svg>',
    USSD: '<svg viewBox="0 0 24 24"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M10 15h.01M14 15h.01M10 18h.01M14 18h.01"/></svg>',
    SMS: '<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></svg>',
    VOICE: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  };
  const subs = { WEB: "SMARTPHONE", USSD: "NO DATA", SMS: "ANY PHONE", VOICE: "PIDGIN · ENGLISH" };
  const pos = { WEB: [-260, -60], USSD: [-60, -260], SMS: [140, -60], VOICE: [-60, 140] };
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "traces");
  svg.setAttribute("viewBox", "0 0 900 900");
  Object.values(pos).forEach(([x, y]) => {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", `M450 450 L${510 + x} ${510 + y}`);
    svg.append(p);
  });
  boardIso.append(svg, box(200, 200, 46, { cls: "chipbox core", top: '<span style="font-size:16px;letter-spacing:.2em">VOTETRAIL</span><small>AI READS · RULES DECIDE</small>' }));
  Object.entries(pos).forEach(([k, [x, y]], i) => {
    const c = box(120, 120, 28, { cls: "chipbox float", x, y, top: `${icons[k]}${k}<small>${subs[k]}</small>` });
    c.style.animationDelay = `${i * -1.2}s`;
    boardIso.append(c);
  });
}

// ---------- scroll story ----------
const story = $(".lp-story");
const stage = $(".lp-stage");
if (story && stage) {
  const scenes = $$(".lp-scene", stage), steps = $$(".lp-step", story), bar = $(".lp-steps .bar");

  // Scene 2: a basic phone as a real 3D slab, with a keypad.
  const keys = "123456789*0#".split("").map((k) => `<i>${k}</i>`).join("");
  $("#fphone").append(box(250, 470, 24, { cls: "fphone", radius: 26, top: `<div class="fscreen" id="ussd"></div><div class="keys">${keys}</div>` }));
  const ussd = JSON.parse($("#ussd-data")?.textContent || "[]");

  // Scene 4: forwarded copies of one message.
  const fw = $("#fwds");
  for (let i = 0; i < 14; i++) {
    const f = el("lp-fwd", `<div class="tag-f">↪ Forwarded many times</div>`);
    f.append(document.createTextNode(fw.dataset.text));
    const a = (i / 14) * Math.PI * 2;
    f.dataset.spread = `translate3d(${Math.cos(a) * 190}px,${Math.sin(a) * 150}px,${-i * 25}px) rotateZ(${Math.sin(i * 7) * 14}deg) rotateY(${Math.cos(i) * 20}deg)`;
    f.dataset.stack = `translate3d(0,${i * -2}px,${-i * 2}px)`;
    f.style.transform = f.dataset.spread;
    fw.append(f);
  }

  let timers = [];
  const later = (fn, ms) => timers.push(setTimeout(fn, ms));
  const typeTo = (node, text, speed) => new Promise((done) => {
    let i = 0;
    const t = () => { node.textContent = text.slice(0, ++i); i < text.length ? later(t, speed) : done(); };
    t();
  });
  const screen = (s) => s.replace(/^(CON|END) /, "");

  const enter = [
    null,
    async () => {
      const s = $("#ussd");
      s.classList.add("cursor");
      const run = [ussd[3], ussd[4], ussd[5]].filter(Boolean);
      for (const [i, step] of run.entries()) {
        await new Promise((r) => later(r, i ? 1200 : 200));
        await typeTo(s, step.input, 90);
        await new Promise((r) => later(r, 450));
        await typeTo(s, screen(step.screen), 14);
      }
    },
    () => $$("#lp-results [data-to]").forEach((d, i) => later(() => window.vtDecrypt?.(d, { duration: 900 }), 300 + i * 80)),
    () => {
      const fs = $$(".lp-fwd"), n = $("#fcount"), l = $("#flabel");
      fs.forEach((f) => (f.style.transform = f.dataset.spread));
      n.textContent = `${fw.dataset.forwards}×`; l.textContent = "FORWARDS";
      later(() => fs.forEach((f) => (f.style.transform = f.dataset.stack)), 1100);
      later(() => { n.textContent = fw.dataset.origins; l.textContent = "INDEPENDENT SOURCE"; }, 1900);
    },
  ];

  let cur = -1;
  const update = () => {
    const total = story.offsetHeight - innerHeight;
    if (total <= 0) return;
    const p = Math.min(1, Math.max(0, -story.getBoundingClientRect().top / total));
    const idx = Math.min(scenes.length - 1, Math.floor(p * scenes.length * 0.999));
    bar.style.height = `${p * 100}%`;
    if (idx === cur) return;
    cur = idx;
    timers.forEach(clearTimeout);
    timers = [];
    scenes.forEach((s, i) => { s.classList.toggle("on", i === idx); s.classList.toggle("past", i < idx); s.classList.toggle("next", i > idx); });
    steps.forEach((s, i) => s.classList.toggle("on", i === idx));
    enter[idx]?.();
  };
  addEventListener("scroll", update, { passive: true });
  addEventListener("resize", update);
  update();
  steps.forEach((s, i) => s.addEventListener("click", () => {
    const total = story.offsetHeight - innerHeight;
    scrollTo({ top: story.offsetTop + total * ((i + 0.5) / scenes.length), behavior: calm() ? "auto" : "smooth" });
  }));
}

// Header links glide to their section.
$$('a[href^="#"]').forEach((a) => a.addEventListener("click", (e) => {
  const target = document.getElementById(a.getAttribute("href").slice(1));
  if (!target) return;
  e.preventDefault();
  target.scrollIntoView({ behavior: calm() ? "auto" : "smooth" });
  history.replaceState(null, "", a.getAttribute("href"));
}));
