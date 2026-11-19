const $ = (id) => document.getElementById(id);
const display = $("sim-display");
const input = $("sim-input");
let session = null;
let path = [];

const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
const phone = () => $("sim-phone").value.trim();

async function post(url, data) {
  const body = new URLSearchParams(data);
  const res = await fetch(url, { method: "POST", body, headers: { "X-CSRFToken": decodeURIComponent(csrf()) }, credentials: "same-origin" });
  return res.json();
}

function reset(msg) {
  session = null; path = [];
  display.textContent = msg || `Dial ${input.placeholder}`;
  input.value = ""; input.placeholder = input.placeholder.startsWith("*") ? input.placeholder : "";
}

let busy = false;

async function ussd(entry) {
  if (busy) return;  // like a real phone: one request at a time
  busy = true;
  $("sim-send").disabled = true;
  try { await ussdStep(entry); } finally { busy = false; $("sim-send").disabled = false; }
}

async function ussdStep(entry) {
  if (!session) {
    if (!/^\*[\d*]+#$/.test(entry)) { display.textContent = "Dial the service code, e.g. *384*2027#"; return; }
    session = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
    path = [];
  } else {
    path.push(entry);
  }
  display.textContent = "Connecting…";
  const r = await post("/api/simulator/ussd", { sessionId: session, phoneNumber: phone(), text: path.join("*") });
  const reply = r.reply || "END Network error";
  display.textContent = reply.slice(4);
  if (reply.startsWith("END")) { session = null; path = []; setTimeout(inbox, 800); }
  input.value = "";
}

async function inbox() {
  const res = await fetch(`/api/simulator/inbox?phone=${encodeURIComponent(phone())}`, { credentials: "same-origin" });
  const data = await res.json();
  const list = $("inbox");
  list.innerHTML = "";
  for (const m of data.messages || []) {
    const li = document.createElement("li");
    li.className = "sms";
    const head = document.createElement("div");
    head.className = "mono mute"; head.style.fontSize = ".75rem";
    head.textContent = `${m.channel.toUpperCase()} · ${new Date(m.at).toLocaleTimeString()}`;
    const body = document.createElement("div");
    body.textContent = m.body;
    li.append(head, body);
    if (m.audio_url) {
      const a = document.createElement("audio"); a.controls = true; a.src = m.audio_url; a.preload = "none";
      li.append(a);
    }
    list.append(li);
  }
}

$("sim-form").addEventListener("submit", (e) => { e.preventDefault(); const v = input.value.trim(); if (v) ussd(v); });
$("sim-cancel").addEventListener("click", () => reset());
$("sms-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("sms-text").value.trim();
  if (!text) return;
  await post("/api/simulator/sms", { phoneNumber: phone(), text });
  $("sms-text").value = "";
  inbox();
});
$("sim-phone").addEventListener("change", inbox);
inbox();
setInterval(inbox, 5000);
