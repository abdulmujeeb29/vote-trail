import { recordWav } from "./wav.js";

const $ = (id) => document.getElementById(id);
const csrf = () => decodeURIComponent((document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "");
const lang = () => $("lang").value;
let pc = null, dc = null, mic = null;

function say(text, who = "assistant") {
  if (!text) return;
  const li = document.createElement("li");
  li.className = who; li.textContent = (who === "user" ? "You: " : "") + text;
  $("transcript").append(li);
}

function status(text) { $("orb-status").textContent = text; }

async function callTool(name, args) {
  const res = await fetch(`/api/voice/tool?language=${lang()}`, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ name, arguments: args }),
  });
  return res.json();
}

async function onEvent(e) {
  const ev = JSON.parse(e.data);
  (window.__events ||= []).push(ev.type);
  if (ev.type === "conversation.item.input_audio_transcription.completed") say(ev.transcript, "user");
  if (ev.type === "response.output_audio_transcript.done" || ev.type === "response.audio_transcript.done") {
    say(ev.transcript);
    (window.__answers ||= []).push(ev.transcript);
  }
  if (ev.type === "response.function_call_arguments.done") {
    status("Checking…");
    const output = await callTool(ev.name, ev.arguments);
    (window.__toolCalls ||= []).push({ name: ev.name, output });
    dc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: ev.call_id, output: JSON.stringify(output) } }));
    dc.send(JSON.stringify({ type: "response.create" }));
    status("Listening…");
  }
  if (ev.type === "error") status("Voice error. Try again or use text.");
}

async function start() {
  status("Connecting…");
  const res = await fetch("/api/voice/session", { method: "POST", credentials: "same-origin",
    headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ language: lang() }) });
  const s = await res.json();
  if (!res.ok) { status(s.error || "Voice unavailable."); return; }
  pc = new RTCPeerConnection();
  const audio = new Audio(); audio.autoplay = true;
  pc.ontrack = (e) => { audio.srcObject = e.streams[0]; };
  mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  mic.getTracks().forEach((t) => pc.addTrack(t, mic));
  dc = pc.createDataChannel("oai-events");
  dc.onmessage = onEvent;
  dc.onopen = () => {
    dc.send(JSON.stringify({ type: "session.update", session: { type: "realtime", audio: { input: { transcription: { model: "whisper-1" } } } } }));
    status("Listening… tap to stop");
    window.__voiceReady = true;
    window.__voiceDc = dc;
  };
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  const sdp = await fetch(s.rtc_url, { method: "POST", body: offer.sdp,
    headers: { Authorization: `Bearer ${s.token}`, "Content-Type": "application/sdp" } });
  if (!sdp.ok) { status("Voice unavailable. Use text."); stop(); return; }
  await pc.setRemoteDescription({ type: "answer", sdp: await sdp.text() });
  $("orb").setAttribute("aria-pressed", "true");
}

function stop() {
  dc?.close(); pc?.close(); mic?.getTracks().forEach((t) => t.stop());
  pc = dc = mic = null;
  $("orb").setAttribute("aria-pressed", "false");
  status("Tap to talk");
}

$("orb").addEventListener("click", () => (pc ? stop() : start().catch(() => { status("Microphone or network problem."); stop(); })));

let rec = null;
$("note-btn").addEventListener("click", async () => {
  const btn = $("note-btn"), out = $("note-result");
  if (!rec) {
    try { rec = await recordWav(60); } catch { out.hidden = false; out.textContent = "Allow microphone access to record."; return; }
    btn.textContent = "Stop and send";
    rec.done.then(send);
    return;
  }
  send(await rec.stop());
});

async function send(blob) {
  const btn = $("note-btn"), out = $("note-result");
  rec = null; btn.textContent = "Record voice note"; btn.disabled = true;
  out.hidden = false; out.textContent = "Listening to your note…";
  const fd = new FormData(); fd.append("audio", blob, "note.wav"); fd.append("language", lang());
  const res = await fetch("/api/voice/note", { method: "POST", body: fd, credentials: "same-origin", headers: { "X-CSRFToken": csrf() } });
  const data = await res.json();
  btn.disabled = false;
  out.innerHTML = "";
  const p = (t, cls) => { const el = document.createElement("p"); el.textContent = t; if (cls) el.className = cls; out.append(el); };
  if (!res.ok) { p(data.error || "Something went wrong.", "tone-bad"); return; }
  p(`“${data.transcript}”`, "mono");
  if (data.verdict) { p(data.verdict.headline); data.verdict.reasons.forEach((r) => p(r, "mute")); }
  if (data.answer?.found) { p(data.answer.results[0].text); p(`Source: ${data.answer.results[0].sources[0]}`, "mute"); }
  if (data.answer && !data.answer.found) p(data.answer.say);
}
